"""Modelos de mapeamento reutilizáveis (2B.2, bloco 2).

Um modelo é uma definição (campos canônicos -> nomes de colunas) com nome único e versão de
definição. Alterar o mapeamento de um modelo sobe `definition_version`. Cada aplicação grava na
versão de metadados a referência (template, versão da definição) e o mapeamento copiado, então o
histórico continua reproduzível mesmo se o modelo for editado depois.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application.audit import record_event
from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.tabular import CANONICAL_FIELDS
from engiflow_api.infrastructure.models import DatasetTemplate

MAX_NAME = 120


def _clean_name(name: str) -> str:
    clean = " ".join(name.split())
    if not clean or len(clean) > MAX_NAME:
        raise DomainError(f"Nome do modelo deve ter entre 1 e {MAX_NAME} caracteres.")
    return clean


def clean_mapping(mapping: dict[str, str]) -> dict[str, str]:
    unknown = sorted(set(mapping) - set(CANONICAL_FIELDS))
    if unknown:
        raise DomainError(f"Campos desconhecidos no modelo: {', '.join(unknown)}.")
    clean: dict[str, str] = {}
    for field_name, column in mapping.items():
        value = column.strip()
        if not value:
            raise DomainError(f"Coluna vazia para o campo '{field_name}'.")
        clean[field_name] = value
    return clean


def list_templates(db: DbSession) -> list[DatasetTemplate]:
    return list(db.scalars(select(DatasetTemplate).order_by(DatasetTemplate.name)).all())


def get_template(db: DbSession, template_id: str) -> DatasetTemplate:
    template = db.get(DatasetTemplate, template_id)
    if template is None:
        raise DomainError("Modelo não encontrado.")
    return template


def _ensure_unique(db: DbSession, name: str, exclude_id: str | None = None) -> None:
    query = (
        select(func.count())
        .select_from(DatasetTemplate)
        .where(func.lower(DatasetTemplate.name) == name.lower())
    )
    if exclude_id is not None:
        query = query.where(DatasetTemplate.id != exclude_id)
    if db.scalar(query):
        raise DomainError("Já existe um modelo com este nome.")


def create_template(
    db: DbSession,
    *,
    name: str,
    mapping: dict[str, str],
    actor: str,
    correlation_id: str | None,
) -> DatasetTemplate:
    clean_name = _clean_name(name)
    clean = clean_mapping(mapping)
    _ensure_unique(db, clean_name)
    template = DatasetTemplate(name=clean_name, definition=clean, definition_version=1)
    db.add(template)
    try:
        db.flush()
    except IntegrityError as exc:  # corrida: outro pedido criou o mesmo nome
        raise DomainError("Já existe um modelo com este nome.") from exc
    record_event(
        db,
        actor=actor,
        action="template.create",
        resource=f"template:{template.id}",
        result="ok",
        correlation_id=correlation_id,
        details={"name": clean_name, "campos": sorted(clean)},
    )
    return template


def update_template(
    db: DbSession,
    template: DatasetTemplate,
    *,
    name: str | None,
    mapping: dict[str, str] | None,
    actor: str,
    correlation_id: str | None,
) -> DatasetTemplate:
    changes: dict[str, object] = {}
    if name is not None:
        clean_name = _clean_name(name)
        _ensure_unique(db, clean_name, exclude_id=template.id)
        template.name = clean_name
        changes["name"] = clean_name
    if mapping is not None:
        clean = clean_mapping(mapping)
        if clean != dict(template.definition):
            template.definition = clean
            template.definition_version += 1
            changes["definition_version"] = template.definition_version
    if changes:
        record_event(
            db,
            actor=actor,
            action="template.update",
            resource=f"template:{template.id}",
            result="ok",
            correlation_id=correlation_id,
            details=changes,
        )
    db.flush()
    return template
