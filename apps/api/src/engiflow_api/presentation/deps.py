"""Dependências FastAPI: sessão de banco e usuário autenticado."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application.auth import resolve_session
from engiflow_api.infrastructure.db import session_scope
from engiflow_api.infrastructure.models import User

SESSION_COOKIE = "engiflow_session"


class NotAuthenticated(Exception):
    """Sinaliza 401; convertido em Problem Details pelo handler."""


def get_db(request: Request) -> Iterator[DbSession]:
    yield from session_scope(request.app.state.session_factory)


DbDep = Annotated[DbSession, Depends(get_db)]


def get_current_user(request: Request, db: DbDep) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise NotAuthenticated
    user = resolve_session(db, token)
    if user is None:
        raise NotAuthenticated
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
