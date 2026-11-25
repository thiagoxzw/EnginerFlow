"""Rotas de cruzamento entre tabelas (2B.3).

- `lookup/preview`: prévia, não grava nada.
- `lookup/derive`: executa e grava uma tabela derivada com rastreabilidade (nova tabela).
- `lookup/export`: exporta o resultado (CSV ou XLSX) sem gravar nada.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from engiflow_api.application.crossing import (
    LookupSpec,
    create_derived_join,
    create_derived_lookup,
    run_join,
    run_lookup,
)
from engiflow_api.application.data_studio import get_dataset
from engiflow_api.domain import lookup as lk
from engiflow_api.infrastructure.exporters import Sheet, to_csv_bytes, to_xlsx_bytes
from engiflow_api.presentation.deps import CurrentUser, DbDep

router = APIRouter(prefix="/api/v1/crossing", tags=["cruzamento"])

_MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class LookupIn(BaseModel):
    left_id: str = Field(min_length=1, max_length=36)
    right_id: str = Field(min_length=1, max_length=36)
    left_keys: list[str] = Field(min_length=1, max_length=10)
    right_keys: list[str] = Field(min_length=1, max_length=10)
    return_columns: list[str] = Field(default_factory=list, max_length=lk.MAX_RETURN_COLUMNS)
    duplicates: Literal["first", "all", "error"] = "first"
    unmatched: Literal["keep_empty", "drop"] = "keep_empty"


class LookupPreviewOut(BaseModel):
    columns: list[str]
    counts: dict[str, int]
    left_rows_read: int
    output_rows: int
    unmatched_keys: list[str]
    duplicate_keys: list[str]
    sample: list[list[str | None]]


class DerivedOut(BaseModel):
    dataset_id: str
    name: str
    run_id: str
    row_count: int
    counts: dict[str, int]
    result_sha256: str


def _spec(payload: LookupIn) -> LookupSpec:
    return LookupSpec(
        left_keys=tuple(payload.left_keys),
        right_keys=tuple(payload.right_keys),
        return_columns=tuple(payload.return_columns),
        policy=lk.LookupPolicy(duplicates=payload.duplicates, unmatched=payload.unmatched),
    )


def _correlation(request: Request) -> str | None:
    value: str | None = getattr(request.state, "correlation_id", None)
    return value


@router.post("/lookup/preview", response_model=LookupPreviewOut)
def lookup_preview(
    payload: LookupIn,
    user: CurrentUser,
    db: DbDep,
    sample: Annotated[int, Query(ge=1, le=200)] = 50,
) -> LookupPreviewOut:
    left = get_dataset(db, payload.left_id)
    right = get_dataset(db, payload.right_id)
    outcome = run_lookup(db, left, right, _spec(payload))
    result = outcome.result
    return LookupPreviewOut(
        columns=outcome.columns,
        counts=dict(result.counts),
        left_rows_read=outcome.left_rows_read,
        output_rows=len(result.rows),
        unmatched_keys=result.unmatched_keys,
        duplicate_keys=result.duplicate_keys,
        sample=[row for _, row in result.rows[:sample]],
    )


@router.post("/lookup/derive", response_model=DerivedOut, status_code=201)
def lookup_derive(payload: LookupIn, request: Request, user: CurrentUser, db: DbDep) -> DerivedOut:
    left = get_dataset(db, payload.left_id)
    right = get_dataset(db, payload.right_id)
    outcome = create_derived_lookup(
        db,
        left,
        right,
        _spec(payload),
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    return DerivedOut(
        dataset_id=outcome.dataset.id,
        name=outcome.dataset.name,
        run_id=outcome.run.id,
        row_count=outcome.row_count,
        counts=outcome.counts,
        result_sha256=outcome.run.result_sha256,
    )


@router.post("/lookup/export")
def lookup_export(
    payload: LookupIn,
    user: CurrentUser,
    db: DbDep,
    format: Annotated[Literal["csv", "xlsx"], Query()] = "csv",
) -> Response:
    left = get_dataset(db, payload.left_id)
    right = get_dataset(db, payload.right_id)
    outcome = run_lookup(db, left, right, _spec(payload))
    rows = [row for _, row in outcome.result.rows]
    if format == "csv":
        content = to_csv_bytes(outcome.columns, rows)
    else:
        content = to_xlsx_bytes([Sheet("Super-PROCV", outcome.columns, rows)])
    filename = f"super-procv.{format}"
    return Response(
        content=content,
        media_type=_MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class JoinIn(BaseModel):
    left_id: str = Field(min_length=1, max_length=36)
    right_id: str = Field(min_length=1, max_length=36)
    left_keys: list[str] = Field(min_length=1, max_length=10)
    right_keys: list[str] = Field(min_length=1, max_length=10)
    join_type: Literal["inner", "left", "right", "full"] = "inner"


class JoinPreviewOut(BaseModel):
    columns: list[str]
    cardinality: str
    left_rows: int
    right_rows: int
    matched_keys: int
    matched_pairs: int
    left_only_rows: int
    right_only_rows: int
    estimated_rows: int
    notes: list[str]
    sample: list[list[str | None]]


@router.post("/join/preview", response_model=JoinPreviewOut)
def join_preview(
    payload: JoinIn,
    user: CurrentUser,
    db: DbDep,
    sample: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JoinPreviewOut:
    """Cardinalidade e linhas estimadas antes da confirmação. Não grava nada."""
    left = get_dataset(db, payload.left_id)
    right = get_dataset(db, payload.right_id)
    outcome = run_join(
        db, left, right, tuple(payload.left_keys), tuple(payload.right_keys), payload.join_type
    )
    plan = outcome.plan
    return JoinPreviewOut(
        columns=outcome.columns,
        cardinality=plan.cardinality,
        left_rows=plan.left_rows,
        right_rows=plan.right_rows,
        matched_keys=plan.matched_keys,
        matched_pairs=plan.matched_pairs,
        left_only_rows=plan.left_only_rows,
        right_only_rows=plan.right_only_rows,
        estimated_rows=plan.estimated_rows,
        notes=plan.notes,
        sample=outcome.rows[:sample],
    )


@router.post("/join/derive", response_model=DerivedOut, status_code=201)
def join_derive(payload: JoinIn, request: Request, user: CurrentUser, db: DbDep) -> DerivedOut:
    left = get_dataset(db, payload.left_id)
    right = get_dataset(db, payload.right_id)
    outcome = create_derived_join(
        db,
        left,
        right,
        tuple(payload.left_keys),
        tuple(payload.right_keys),
        payload.join_type,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    return DerivedOut(
        dataset_id=outcome.dataset.id,
        name=outcome.dataset.name,
        run_id=outcome.run.id,
        row_count=outcome.row_count,
        counts=outcome.counts,
        result_sha256=outcome.run.result_sha256,
    )
