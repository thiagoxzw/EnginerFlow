"""Autenticação de usuário único: login, logout e validação de sessão."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application.security import (
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)
from engiflow_api.infrastructure.models import Session as AuthSession
from engiflow_api.infrastructure.models import User


def create_user(db: DbSession, *, email: str, display_name: str, password: str) -> User:
    if db.scalar(select(User).limit(1)) is not None:
        raise ValueError("Já existe um usuário. O EngiFlow é de uso individual (ADR-0012).")
    if len(password) < 12:
        raise ValueError("A senha deve ter pelo menos 12 caracteres.")
    user = User(
        email=email.strip().lower(),
        display_name=display_name,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    return user


def login(db: DbSession, *, email: str, password: str, ttl_hours: int) -> tuple[User, str] | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(user.password_hash, password):
        return None
    token = new_session_token()
    now = datetime.now(UTC)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(hours=ttl_hours),
        )
    )
    db.flush()
    return user, token


def resolve_session(db: DbSession, token: str) -> User | None:
    now = datetime.now(UTC)
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if row is None or row.revoked_at is not None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires <= now:
        return None
    return db.get(User, row.user_id)


def revoke_session(db: DbSession, token: str) -> None:
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
