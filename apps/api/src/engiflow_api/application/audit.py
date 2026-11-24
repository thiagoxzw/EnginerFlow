"""Auditoria: registra operações sem vazar segredos (ADR-0012, SECURITY_MODEL §8)."""

import re
from typing import Any

from sqlalchemy.orm import Session

from engiflow_api.infrastructure.models import AuditLog

_SENSITIVE_KEYS = re.compile(
    r"(password|senha|token|secret|key|authorization|cookie)", re.IGNORECASE
)
_MAX_STRING = 500


def redact(value: Any) -> Any:
    """Mascara chaves sensíveis e trunca strings longas (ex.: conteúdo de planilha)."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            out[key] = "***" if _SENSITIVE_KEYS.search(key) else redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str) and len(value) > _MAX_STRING:
        return value[:_MAX_STRING] + "...[truncado]"
    return value


def record_event(
    db: Session,
    *,
    actor: str,
    action: str,
    resource: str,
    result: str,
    correlation_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            resource=resource,
            result=result,
            correlation_id=correlation_id,
            details=redact(details or {}),
        )
    )
