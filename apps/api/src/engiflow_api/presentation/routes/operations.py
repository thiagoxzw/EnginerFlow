"""Rotas de versionamento e transformações (2B.1).

Toda mudança exige `base_version_id` (versão que o cliente viu). Operações que mudam dados
aceitam `Idempotency-Key`. Erros de concorrência retornam 409.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, Field

from engiflow_api.application import versioning
from engiflow_api.application.data_studio import get_dataset
from engiflow_api.application.operations.registry import OPERATIONS
from engiflow_api.infrastructure.models import DatasetOperation, DatasetPreview
from engiflow_api.presentation.deps import CurrentUser, DbDep

router = APIRouter(prefix="/api/v1", tags=["transformacoes"])


class CatalogItem(BaseModel):
    code: str
    version: int
    description: str
    reversible: bool
    params_schema: dict[str, Any]


class VersionOut(BaseModel):
    id: str
    number: int
    parent_version_id: str | None
    row_count: int
    content_sha256: str
    created_at: datetime
    is_current: bool


class PreviewIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    base_version_id: str
    base_metadata_version_id: str | None = None


class PreviewOut(BaseModel):
    preview_id: str
    expires_at: datetime
    rows_affected: int
    cells_changed: int
    before_content_sha256: str
    after_content_sha256: str


class ApplyIn(BaseModel):
    preview_id: str
    base_version_id: str
    base_metadata_version_id: str | None = None


class OperationOut(BaseModel):
    id: str
    seq: int
    code: str
    code_version: int
    status: str
    before_version_id: str
    after_version_id: str
    rows_affected: int
    cells_changed: int
    created_at: datetime


class ApplyOut(BaseModel):
    created: bool
    current_version_id: str
    current_metadata_version_id: str
    content_sha256: str
    operation: OperationOut


class VersionMoveIn(BaseModel):
    base_version_id: str
    base_metadata_version_id: str | None = None


class VersionMoveOut(BaseModel):
    current_version_id: str
    current_metadata_version_id: str


def _operation_out(op: DatasetOperation) -> OperationOut:
    return OperationOut(
        id=op.id,
        seq=op.seq,
        code=op.code,
        code_version=op.code_version,
        status=op.status,
        before_version_id=op.before_version_id,
        after_version_id=op.after_version_id,
        rows_affected=op.rows_affected,
        cells_changed=op.cells_changed,
        created_at=op.created_at,
    )


def _correlation(request: Request) -> str | None:
    value: str | None = getattr(request.state, "correlation_id", None)
    return value


@router.get("/operations/catalog", response_model=list[CatalogItem])
def catalog(user: CurrentUser) -> list[CatalogItem]:
    return [
        CatalogItem(
            code=spec.code,
            version=spec.version,
            description=spec.description,
            reversible=spec.reversible,
            params_schema=spec.params_model.model_json_schema(),
        )
        for spec in OPERATIONS.values()
    ]


class MetadataVersionOut(BaseModel):
    id: str
    version_id: str
    number: int
    parent_metadata_version_id: str | None
    columns: list[str]
    mapping: dict[str, str]
    header_row: int | None
    metadata_sha256: str
    template_id: str | None
    actor: str
    created_at: datetime
    is_current: bool


@router.get("/datasets/{dataset_id}/metadata-versions", response_model=list[MetadataVersionOut])
def metadata_versions(dataset_id: str, user: CurrentUser, db: DbDep) -> list[MetadataVersionOut]:
    dataset = get_dataset(db, dataset_id)
    return [
        MetadataVersionOut(
            id=m.id,
            version_id=m.version_id,
            number=m.number,
            parent_metadata_version_id=m.parent_metadata_version_id,
            columns=list(m.columns),
            mapping=dict(m.mapping or {}),
            header_row=m.header_row,
            metadata_sha256=m.metadata_sha256,
            template_id=m.template_id,
            actor=m.actor,
            created_at=m.created_at,
            is_current=m.id == dataset.current_metadata_version_id,
        )
        for m in versioning.list_metadata_versions(db, dataset.id)
    ]


@router.get("/datasets/{dataset_id}/versions", response_model=list[VersionOut])
def versions(dataset_id: str, user: CurrentUser, db: DbDep) -> list[VersionOut]:
    dataset = get_dataset(db, dataset_id)
    return [
        VersionOut(
            id=v.id,
            number=v.number,
            parent_version_id=v.parent_version_id,
            row_count=v.row_count,
            content_sha256=v.content_sha256,
            created_at=v.created_at,
            is_current=v.id == dataset.current_version_id,
        )
        for v in versioning.list_versions(db, dataset.id)
    ]


@router.post("/datasets/{dataset_id}/operations/preview", response_model=PreviewOut)
def preview(
    dataset_id: str, payload: PreviewIn, request: Request, user: CurrentUser, db: DbDep
) -> PreviewOut:
    dataset = get_dataset(db, dataset_id)
    created: DatasetPreview = versioning.create_preview(
        db,
        dataset,
        code=payload.code,
        raw_params=payload.params,
        base_version_id=payload.base_version_id,
        base_metadata_version_id=payload.base_metadata_version_id,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    base = versioning.current_version(db, dataset)
    return PreviewOut(
        preview_id=created.id,
        expires_at=created.expires_at,
        rows_affected=created.rows_affected,
        cells_changed=created.cells_changed,
        before_content_sha256=base.content_sha256,
        after_content_sha256=created.after_content_sha256,
    )


@router.post("/datasets/{dataset_id}/operations", response_model=ApplyOut, status_code=201)
def apply(
    dataset_id: str,
    payload: ApplyIn,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> ApplyOut:
    dataset = get_dataset(db, dataset_id)
    outcome = versioning.apply_preview(
        db,
        dataset,
        preview_id=payload.preview_id,
        base_version_id=payload.base_version_id,
        base_metadata_version_id=payload.base_metadata_version_id,
        idempotency_key=idempotency_key,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    if not outcome.created:
        response.status_code = 200
    return ApplyOut(
        created=outcome.created,
        current_version_id=dataset.current_version_id or "",
        current_metadata_version_id=dataset.current_metadata_version_id or "",
        content_sha256=outcome.version.content_sha256,
        operation=_operation_out(outcome.operation),
    )


@router.get("/datasets/{dataset_id}/operations", response_model=list[OperationOut])
def operations(dataset_id: str, user: CurrentUser, db: DbDep) -> list[OperationOut]:
    dataset = get_dataset(db, dataset_id)
    return [_operation_out(op) for op in versioning.list_operations(db, dataset.id)]


@router.post("/datasets/{dataset_id}/undo", response_model=VersionMoveOut)
def undo(
    dataset_id: str, payload: VersionMoveIn, request: Request, user: CurrentUser, db: DbDep
) -> VersionMoveOut:
    dataset = get_dataset(db, dataset_id)
    target = versioning.undo(
        db,
        dataset,
        base_version_id=payload.base_version_id,
        base_metadata_version_id=payload.base_metadata_version_id,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    return VersionMoveOut(
        current_version_id=target.data_version_id,
        current_metadata_version_id=target.metadata_version_id,
    )


@router.post("/datasets/{dataset_id}/redo", response_model=VersionMoveOut)
def redo(
    dataset_id: str, payload: VersionMoveIn, request: Request, user: CurrentUser, db: DbDep
) -> VersionMoveOut:
    dataset = get_dataset(db, dataset_id)
    target = versioning.redo(
        db,
        dataset,
        base_version_id=payload.base_version_id,
        base_metadata_version_id=payload.base_metadata_version_id,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    return VersionMoveOut(
        current_version_id=target.data_version_id,
        current_metadata_version_id=target.metadata_version_id,
    )
