"""Rotas de cruzamento entre tabelas (2B.3). A prévia não grava nada."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from engiflow_api.application.crossing import LookupSpec, run_lookup
from engiflow_api.application.data_studio import get_dataset
from engiflow_api.domain import lookup as lk
from engiflow_api.presentation.deps import CurrentUser, DbDep

router = APIRouter(prefix="/api/v1/crossing", tags=["cruzamento"])


class LookupPreviewIn(BaseModel):
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


@router.post("/lookup/preview", response_model=LookupPreviewOut)
def lookup_preview(
    payload: LookupPreviewIn,
    user: CurrentUser,
    db: DbDep,
    sample: Annotated[int, Query(ge=1, le=200)] = 50,
) -> LookupPreviewOut:
    left = get_dataset(db, payload.left_id)
    right = get_dataset(db, payload.right_id)
    spec = LookupSpec(
        left_keys=tuple(payload.left_keys),
        right_keys=tuple(payload.right_keys),
        return_columns=tuple(payload.return_columns),
        policy=lk.LookupPolicy(duplicates=payload.duplicates, unmatched=payload.unmatched),
    )
    outcome = run_lookup(db, left, right, spec)
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
