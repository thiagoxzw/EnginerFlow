"""Rotas de modelos de mapeamento reutilizáveis (2B.2, bloco 2).

A aplicação de um modelo passa pelo fluxo normal de prévia e aplicação de operações; aqui só
se gera a prévia com o mapeamento copiado do modelo no momento.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from engiflow_api.application import versioning
from engiflow_api.application.data_studio import get_dataset
from engiflow_api.application.templates import (
    create_template,
    get_template,
    list_templates,
    update_template,
)
from engiflow_api.infrastructure.models import DatasetTemplate
from engiflow_api.presentation.deps import CurrentUser, DbDep

router = APIRouter(prefix="/api/v1", tags=["modelos"])


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mapping: dict[str, str] = Field(default_factory=dict)


class TemplatePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    mapping: dict[str, str] | None = None


class TemplateOut(BaseModel):
    id: str
    name: str
    mapping: dict[str, str]
    definition_version: int
    updated_at: datetime


class TemplatePreviewIn(BaseModel):
    base_version_id: str
    base_metadata_version_id: str | None = None
    allow_missing: bool = False


class TemplatePreviewOut(BaseModel):
    # Sem `preview_id` quando há colunas ausentes sem confirmação: a prévia não é gerada e a
    # interface pede confirmação e refaz a prévia com `allow_missing=true`.
    preview_id: str | None
    expires_at: datetime | None
    template_id: str
    definition_version: int
    missing_fields: dict[str, str]


def _out(template: DatasetTemplate) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        mapping=dict(template.definition),
        definition_version=template.definition_version,
        updated_at=template.updated_at,
    )


def _correlation(request: Request) -> str | None:
    value: str | None = getattr(request.state, "correlation_id", None)
    return value


@router.get("/templates", response_model=list[TemplateOut])
def templates(user: CurrentUser, db: DbDep) -> list[TemplateOut]:
    return [_out(t) for t in list_templates(db)]


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create(payload: TemplateIn, request: Request, user: CurrentUser, db: DbDep) -> TemplateOut:
    template = create_template(
        db,
        name=payload.name,
        mapping=payload.mapping,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    return _out(template)


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def patch(
    template_id: str, payload: TemplatePatch, request: Request, user: CurrentUser, db: DbDep
) -> TemplateOut:
    template = get_template(db, template_id)
    update_template(
        db,
        template,
        name=payload.name,
        mapping=payload.mapping,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    return _out(template)


@router.post(
    "/datasets/{dataset_id}/templates/{template_id}/preview", response_model=TemplatePreviewOut
)
def preview_template(
    dataset_id: str,
    template_id: str,
    payload: TemplatePreviewIn,
    request: Request,
    user: CurrentUser,
    db: DbDep,
) -> TemplatePreviewOut:
    dataset = get_dataset(db, dataset_id)
    template = get_template(db, template_id)
    mapping: dict[str, str] = dict(template.definition)
    missing = {f: c for f, c in mapping.items() if c not in dataset.columns}
    if missing and not payload.allow_missing:
        # Sem confirmação não há prévia: nada é aplicável e a interface pede confirmação.
        return TemplatePreviewOut(
            preview_id=None,
            expires_at=None,
            template_id=template.id,
            definition_version=template.definition_version,
            missing_fields=missing,
        )
    params: dict[str, Any] = {
        "template_id": template.id,
        "definition_version": template.definition_version,
        "mapping": mapping,
        "allow_missing": payload.allow_missing,
    }
    created = versioning.create_preview(
        db,
        dataset,
        code="apply_mapping_template",
        raw_params=params,
        base_version_id=payload.base_version_id,
        base_metadata_version_id=payload.base_metadata_version_id,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    return TemplatePreviewOut(
        preview_id=created.id,
        expires_at=created.expires_at,
        template_id=template.id,
        definition_version=template.definition_version,
        missing_fields=missing,
    )
