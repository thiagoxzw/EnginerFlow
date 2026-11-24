"""Rotas do Data Studio (/api/v1/datasets)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from engiflow_api.application.data_studio import (
    compare_datasets,
    find_duplicates,
    get_dataset,
    import_file,
    set_mapping,
)
from engiflow_api.core.config import get_settings
from engiflow_api.domain.errors import DomainError
from engiflow_api.infrastructure.models import Dataset, DatasetRow
from engiflow_api.infrastructure.readers import ImportLimits
from engiflow_api.presentation.deps import CurrentUser, DbDep

router = APIRouter(prefix="/api/v1/datasets", tags=["data-studio"])

_PREVIEW_ROWS = 20
_LIST_LIMIT = 1000


class DatasetSummary(BaseModel):
    id: str
    name: str
    source_filename: str
    file_kind: str
    sheet_name: str | None
    columns: list[str]
    row_count: int
    mapping: dict[str, str]
    warnings: list[str]
    created_at: datetime


class DatasetDetail(DatasetSummary):
    preview: list[dict[str, Any]]


class ImportOut(BaseModel):
    created: bool
    dataset: DatasetSummary


class MappingIn(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class RowOut(BaseModel):
    row_number: int
    values: list[str]


class RowsOut(BaseModel):
    total: int
    offset: int
    limit: int
    columns: list[str]
    rows: list[RowOut]


class ExactGroupOut(BaseModel):
    key: str
    row_numbers: list[int]
    values: list[str]


class LeadingZeroOut(BaseModel):
    key_a: str
    key_b: str


class SimilarOut(BaseModel):
    row_a: int
    row_b: int
    value_a: str
    value_b: str
    score: float
    shared_tokens: list[str]


class DuplicatesOut(BaseModel):
    exact_codes: list[ExactGroupOut]
    leading_zero_suspicions: list[LeadingZeroOut]
    similar_descriptions: list[SimilarOut]
    note: str


class CompareIn(BaseModel):
    left_id: str
    right_id: str


class CompareOut(BaseModel):
    only_left_count: int
    only_right_count: int
    in_both_count: int
    only_left: list[str]
    only_right: list[str]
    leading_zero_candidates: list[dict[str, str]]
    note: str


def _summary(dataset: Dataset) -> DatasetSummary:
    return DatasetSummary(
        id=dataset.id,
        name=dataset.name,
        source_filename=dataset.source_filename,
        file_kind=dataset.file_kind,
        sheet_name=dataset.sheet_name,
        columns=list(dataset.columns),
        row_count=dataset.row_count,
        mapping=dict(dataset.mapping),
        warnings=list(dataset.warnings),
        created_at=dataset.created_at,
    )


def _correlation(request: Request) -> str | None:
    value: str | None = getattr(request.state, "correlation_id", None)
    return value


@router.post("", status_code=201, response_model=ImportOut)
def upload(
    file: UploadFile,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbDep,
    sheet: Annotated[str | None, Form()] = None,
) -> ImportOut:
    settings = get_settings()
    limits = ImportLimits(
        max_upload_bytes=settings.max_upload_mb * 1024 * 1024, max_rows=settings.max_rows
    )
    data = file.file.read(limits.max_upload_bytes + 1)
    if len(data) > limits.max_upload_bytes:
        raise DomainError(f"Arquivo excede o limite de {settings.max_upload_mb} MB.")
    if not data:
        raise DomainError("Arquivo vazio.")
    correlation_id = _correlation(request)
    result = import_file(
        db,
        actor=user.email,
        filename=file.filename or "tabela",
        data=data,
        sheet=sheet or None,
        limits=limits,
        storage_dir=Path(settings.data_dir) / "originals",
        correlation_id=correlation_id,
    )
    db.commit()
    if not result.created:
        response.status_code = 200
    return ImportOut(created=result.created, dataset=_summary(result.dataset))


@router.get("", response_model=list[DatasetSummary])
def list_datasets(user: CurrentUser, db: DbDep) -> list[DatasetSummary]:
    rows = db.scalars(select(Dataset).order_by(Dataset.created_at.desc()).limit(200)).all()
    return [_summary(d) for d in rows]


@router.get("/{dataset_id}", response_model=DatasetDetail)
def detail(dataset_id: str, user: CurrentUser, db: DbDep) -> DatasetDetail:
    dataset = get_dataset(db, dataset_id)
    preview_rows = db.execute(
        select(DatasetRow.values)
        .where(DatasetRow.dataset_id == dataset.id)
        .order_by(DatasetRow.row_number)
        .limit(_PREVIEW_ROWS)
    ).all()
    preview = [dict(zip(dataset.columns, values[0], strict=False)) for values in preview_rows]
    base = _summary(dataset).model_dump()
    return DatasetDetail(**base, preview=preview)


@router.get("/{dataset_id}/rows", response_model=RowsOut)
def rows(
    dataset_id: str,
    user: CurrentUser,
    db: DbDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> RowsOut:
    dataset = get_dataset(db, dataset_id)
    total = (
        db.scalar(
            select(func.count()).select_from(DatasetRow).where(DatasetRow.dataset_id == dataset.id)
        )
        or 0
    )
    page = db.execute(
        select(DatasetRow.row_number, DatasetRow.values)
        .where(DatasetRow.dataset_id == dataset.id)
        .order_by(DatasetRow.row_number)
        .offset(offset)
        .limit(limit)
    ).all()
    return RowsOut(
        total=int(total),
        offset=offset,
        limit=limit,
        columns=list(dataset.columns),
        rows=[RowOut(row_number=n, values=list(v)) for n, v in page],
    )


@router.put("/{dataset_id}/mapping", response_model=DatasetSummary)
def mapping(
    dataset_id: str, payload: MappingIn, request: Request, user: CurrentUser, db: DbDep
) -> DatasetSummary:
    dataset = get_dataset(db, dataset_id)
    correlation_id = _correlation(request)
    set_mapping(db, dataset, payload.mapping, actor=user.email, correlation_id=correlation_id)
    db.commit()
    return _summary(dataset)


@router.get("/{dataset_id}/duplicates", response_model=DuplicatesOut)
def duplicates(
    dataset_id: str,
    user: CurrentUser,
    db: DbDep,
    threshold: Annotated[float, Query(ge=0.5, le=1.0)] = 0.85,
    descriptions: Annotated[bool, Query()] = True,
) -> DuplicatesOut:
    dataset = get_dataset(db, dataset_id)
    report = find_duplicates(db, dataset, threshold=threshold, check_descriptions=descriptions)
    return DuplicatesOut(
        exact_codes=[
            ExactGroupOut(key=g.key, row_numbers=g.row_numbers, values=g.values)
            for g in report.exact_codes
        ],
        leading_zero_suspicions=[
            LeadingZeroOut(key_a=s.key_a, key_b=s.key_b) for s in report.leading_zero_suspicions
        ],
        similar_descriptions=[
            SimilarOut(
                row_a=p.row_a,
                row_b=p.row_b,
                value_a=p.value_a,
                value_b=p.value_b,
                score=p.score,
                shared_tokens=p.shared_tokens,
            )
            for p in report.similar_descriptions
        ],
        note=(
            "Duplicatas e semelhanças são sugestões para revisão humana. Nenhum registro é "
            "removido nem considerado equivalente automaticamente."
        ),
    )


@router.post("/compare", response_model=CompareOut)
def compare(payload: CompareIn, user: CurrentUser, db: DbDep) -> CompareOut:
    left = get_dataset(db, payload.left_id)
    right = get_dataset(db, payload.right_id)
    for dataset in (left, right):
        if "code" not in dataset.mapping:
            raise DomainError(
                f"A tabela '{dataset.name}' não tem o campo 'code' mapeado. "
                "Mapeie antes de comparar."
            )
    result = compare_datasets(db, left, right)
    return CompareOut(
        only_left_count=len(result.only_left),
        only_right_count=len(result.only_right),
        in_both_count=len(result.in_both),
        only_left=result.only_left[:_LIST_LIMIT],
        only_right=result.only_right[:_LIST_LIMIT],
        leading_zero_candidates=[
            {"esquerda": a, "direita": b} for a, b in result.leading_zero_candidates[:_LIST_LIMIT]
        ],
        note=(
            "Comparação por chave de código (sem diferença de caixa, zeros preservados). "
            "Candidatos por zeros à esquerda exigem confirmação humana."
        ),
    )
