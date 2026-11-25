"""Fixtures. Por padrão usa SQLite em arquivo temporário; defina ENGIFLOW_TEST_DATABASE_URL
para rodar contra PostgreSQL real (ex.: no CI)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from engiflow_api.application.auth import create_user
from engiflow_api.core.config import Settings
from engiflow_api.infrastructure.db import build_session_factory
from engiflow_api.infrastructure.models import Base
from engiflow_api.main import create_app

PASSWORD = "senha-forte-de-teste-123"
EMAIL = "usuario@example.com"


@pytest.fixture
def database_url(tmp_path: Path) -> Iterator[str]:
    url = os.environ.get("ENGIFLOW_TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        engine.dispose()
        yield url
        return
    yield f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    eng = create_engine(database_url)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker:  # type: ignore[type-arg]
    return build_session_factory(engine)


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(database_url=database_url, frontend_origin="http://127.0.0.1:3000")


@pytest.fixture
def app(settings: Settings, session_factory: sessionmaker) -> FastAPI:  # type: ignore[type-arg]
    return create_app(settings=settings, session_factory=session_factory)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def user(session_factory: sessionmaker) -> None:  # type: ignore[type-arg]
    with session_factory() as db:
        create_user(db, email=EMAIL, display_name="Usuário de teste", password=PASSWORD)
        db.commit()


@pytest.fixture
def logged_client(client: TestClient, user: None) -> TestClient:
    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return client


@pytest.fixture
def storage_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Configuração com pasta de armazenamento temporária para testes de upload e operações."""
    settings = Settings(
        database_url="sqlite:///unused",
        data_dir=str(tmp_path / "data"),
        max_upload_mb=5,
        max_rows=500_000,
    )
    monkeypatch.setattr("engiflow_api.presentation.routes.datasets.get_settings", lambda: settings)
    monkeypatch.setattr(
        "engiflow_api.presentation.routes.operations.get_settings", lambda: settings
    )
    return settings
