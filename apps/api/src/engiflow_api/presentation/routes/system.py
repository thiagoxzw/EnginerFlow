"""Health, readiness, autenticação e dashboard."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, text

from engiflow_api.application.audit import record_event
from engiflow_api.application.auth import login, revoke_session
from engiflow_api.core.config import get_settings
from engiflow_api.infrastructure.models import AuditLog
from engiflow_api.presentation.deps import SESSION_COOKIE, CurrentUser, DbDep
from engiflow_api.presentation.middleware import log as http_log

router = APIRouter()


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    email: str
    display_name: str


class AuditEntryOut(BaseModel):
    occurred_at: datetime
    action: str
    resource: str
    result: str


class DashboardOut(BaseModel):
    user: UserOut
    system: dict[str, Any]
    activity_last_7_days: int
    recent_activity: list[AuditEntryOut]
    note: str


def _correlation(request: Request) -> str | None:
    value: str | None = getattr(request.state, "correlation_id", None)
    return value


@router.get("/health/live", tags=["sistema"])
def live() -> dict[str, str]:
    return {"status": "ok", "version": get_settings().app_version}


@router.get("/health/ready", tags=["sistema"])
def ready(request: Request) -> Response:
    factory = request.app.state.session_factory
    try:
        with factory() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        http_log.exception("readiness falhou ao consultar o banco")
        return Response(
            status_code=503,
            content='{"status":"unavailable","database":"down"}',
            media_type="application/json",
        )
    return Response(
        status_code=200,
        content='{"status":"ready","database":"up"}',
        media_type="application/json",
    )


@router.post("/api/v1/auth/login", tags=["auth"])
def login_route(payload: LoginIn, request: Request, response: Response, db: DbDep) -> UserOut:
    settings = get_settings()
    result = login(
        db,
        email=str(payload.email),
        password=payload.password,
        ttl_hours=settings.session_ttl_hours,
    )
    if result is None:
        record_event(
            db,
            actor=str(payload.email),
            action="auth.login",
            resource="session",
            result="denied",
            correlation_id=_correlation(request),
        )
        # Commit explícito: a exceção abaixo causaria rollback e perderia o registro da tentativa.
        db.commit()
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    user, token = result
    record_event(
        db,
        actor=user.email,
        action="auth.login",
        resource="session",
        result="ok",
        correlation_id=_correlation(request),
    )
    # Commit explícito antes da resposta: a sessão precisa existir para a próxima requisição do
    # navegador. Sem isso, o commit da dependência pode ocorrer depois, e a verificação seguinte
    # (/api/v1/dashboard) recebia 401 e devolvia o usuário ao login.
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return UserOut(email=user.email, display_name=user.display_name)


@router.post("/api/v1/auth/logout", tags=["auth"], status_code=204)
def logout_route(request: Request, db: DbDep) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        revoke_session(db, token)
    record_event(
        db,
        actor="anonymous",
        action="auth.logout",
        resource="session",
        result="ok",
        correlation_id=_correlation(request),
    )
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/api/v1/auth/me", tags=["auth"])
def me(user: CurrentUser) -> UserOut:
    return UserOut(email=user.email, display_name=user.display_name)


@router.get("/api/v1/dashboard", tags=["dashboard"])
def dashboard(user: CurrentUser, db: DbDep) -> DashboardOut:
    since = datetime.now(UTC) - timedelta(days=7)
    count_7d = db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.occurred_at >= since)
    )
    recent = db.scalars(select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(20)).all()
    return DashboardOut(
        user=UserOut(email=user.email, display_name=user.display_name),
        system={"version": get_settings().app_version, "database": "up"},
        activity_last_7_days=int(count_7d or 0),
        recent_activity=[
            AuditEntryOut(
                occurred_at=r.occurred_at,
                action=r.action,
                resource=r.resource,
                result=r.result,
            )
            for r in recent
        ],
        note=(
            "Indicadores de projetos, materiais, BOMs e automações serão exibidos quando os "
            "módulos correspondentes forem implementados. Nenhum número fictício é exibido."
        ),
    )
