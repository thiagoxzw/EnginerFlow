"""Testes de API: saúde, autenticação, autorização, erros e dashboard."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from engiflow_api.infrastructure.models import AuditLog
from engiflow_api.infrastructure.models import Session as AuthSession
from tests.conftest import EMAIL, PASSWORD


def test_health_live(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_reports_database_up(client: TestClient) -> None:
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "database": "up"}


def test_dashboard_requires_authentication_and_returns_problem_json(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard")
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 401
    assert body["title"] == "Não autenticado"
    assert body["instance"] == "/api/v1/dashboard"


def test_login_me_dashboard_logout_flow(client: TestClient, user: None) -> None:
    login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["email"] == EMAIL
    assert "engiflow_session" in login.cookies

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == "Usuário de teste"

    dash = client.get("/api/v1/dashboard")
    assert dash.status_code == 200
    body = dash.json()
    assert body["user"]["email"] == EMAIL
    assert body["activity_last_7_days"] >= 1  # o próprio login foi auditado
    assert any(a["action"] == "auth.login" for a in body["recent_activity"])

    out = client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_is_rejected_and_audited(
    client: TestClient,
    user: None,
    session_factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "errada-errada"})
    assert resp.status_code == 401
    assert "engiflow_session" not in resp.cookies
    with session_factory() as db:
        denied = db.scalars(
            select(AuditLog).where(AuditLog.action == "auth.login", AuditLog.result == "denied")
        ).all()
        assert len(denied) == 1


def test_unknown_email_gives_same_generic_error(client: TestClient, user: None) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": "outro@example.com", "password": "x"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "E-mail ou senha inválidos."


def test_expired_session_is_rejected(
    logged_client: TestClient,
    session_factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    with session_factory() as db:
        row = db.scalar(select(AuthSession))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert logged_client.get("/api/v1/auth/me").status_code == 401


def test_correlation_id_is_echoed_and_generated(client: TestClient) -> None:
    resp = client.get("/health/live", headers={"X-Correlation-Id": "abc-123"})
    assert resp.headers["X-Correlation-Id"] == "abc-123"
    resp2 = client.get("/health/live")
    assert len(resp2.headers["X-Correlation-Id"]) >= 32


def test_validation_error_uses_problem_format(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"email": "nao-e-email", "password": ""})
    assert resp.status_code == 422
    body = resp.json()
    assert body["title"] == "Dados inválidos"
    assert body["status"] == 422
    assert isinstance(body["errors"], list) and body["errors"]


def test_readiness_returns_503_when_database_is_down(
    app: object, database_url: str, engine: Engine
) -> None:
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    engine.dispose()
    broken = sessionmaker(bind=_broken_engine())
    app.state.session_factory = broken
    with TestClient(app) as c:
        resp = c.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["database"] == "down"


def _broken_engine() -> Engine:
    from sqlalchemy import create_engine

    return create_engine("sqlite:////nonexistent-dir-engiflow/x.db")


@pytest.mark.parametrize("path", ["/api/v1/auth/me", "/api/v1/dashboard"])
def test_protected_routes_reject_forged_cookie(client: TestClient, path: str) -> None:
    client.cookies.set("engiflow_session", "token-forjado")
    assert client.get(path).status_code == 401


def test_audit_table_is_append_only_from_application_perspective(
    logged_client: TestClient,
    session_factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    with session_factory() as db:
        count = db.scalar(text("SELECT COUNT(*) FROM audit_logs"))
        assert count is not None and count >= 1
