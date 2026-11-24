"""Casos de uso do Data Studio: importar, mapear, detectar duplicatas e comparar códigos."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application.audit import record_event
from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.tabular import (
    CANONICAL_FIELDS,
    CodeComparison,
    DuplicateGroup,
    LeadingZeroSuspicion,
    SimilarPair,
    compare_codes,
    exact_code_duplicates,
    leading_zero_suspicions,
    similar_descriptions,
    validate_mapping,
)
from engiflow_api.infrastructure.models import Dataset, DatasetRow
from engiflow_api.infrastructure.readers import ImportLimits, detect_kind, read_csv, read_xlsx


@dataclass(frozen=True)
class ImportResult:
    dataset: Dataset
    created: bool


def import_file(
    db: DbSession,
    *,
    actor: str,
    filename: str,
    data: bytes,
    sheet: str | None,
    limits: ImportLimits,
    storage_dir: Path,
    correlation_id: str | None,
) -> ImportResult:
    digest = hashlib.sha256(data).hexdigest()
    sheet_key = sheet or ""
    existing = db.scalar(
        select(Dataset).where(Dataset.source_sha256 == digest, Dataset.sheet_key == sheet_key)
    )
    if existing is not None:
        # Idempotência: o mesmo arquivo (mesmo hash e aba) não gera registros duplicados.
        return ImportResult(dataset=existing, created=False)

    kind = detect_kind(data)
    table = read_csv(data, limits) if kind == "csv" else read_xlsx(data, sheet, limits)

    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / f"{digest}.{kind}").write_bytes(data)

    dataset = Dataset(
        name=Path(filename).stem[:255] or "Tabela",
        source_filename=Path(filename).name[:255],
        source_sha256=digest,
        file_kind=kind,
        sheet_key=sheet_key,
        sheet_name=table.sheet,
        columns=table.columns,
        row_count=len(table.rows),
        mapping={},
        warnings=table.warnings,
    )
    db.add(dataset)
    db.flush()
    db.add_all(
        DatasetRow(dataset_id=dataset.id, row_number=number, values=values)
        for number, values in zip(table.row_numbers, table.rows, strict=True)
    )
    record_event(
        db,
        actor=actor,
        action="data_studio.import",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={
            "filename": dataset.source_filename,
            "sha256": digest,
            "kind": kind,
            "sheet": table.sheet,
            "rows": len(table.rows),
            "columns": len(table.columns),
        },
    )
    return ImportResult(dataset=dataset, created=True)


def get_dataset(db: DbSession, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise DomainError("Tabela não encontrada.")
    return dataset


def set_mapping(
    db: DbSession,
    dataset: Dataset,
    mapping: dict[str, str],
    *,
    actor: str,
    correlation_id: str | None,
) -> Dataset:
    clean = validate_mapping(mapping, dataset.columns)
    previous = dict(dataset.mapping)
    dataset.mapping = clean
    record_event(
        db,
        actor=actor,
        action="data_studio.mapping",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={"antes": previous, "depois": clean},
    )
    return dataset


def _column_index(dataset: Dataset, field_name: str) -> int:
    if field_name not in CANONICAL_FIELDS:
        raise DomainError(f"Campo desconhecido: {field_name}.")
    column = dataset.mapping.get(field_name)
    if column is None:
        raise DomainError(
            f"Campo '{field_name}' não mapeado nesta tabela. Defina o mapeamento primeiro."
        )
    return dataset.columns.index(column)


def field_items(db: DbSession, dataset: Dataset, field_name: str) -> list[tuple[int, str]]:
    """Pares (linha na origem, valor) do campo mapeado. Valores vazios são mantidos."""
    index = _column_index(dataset, field_name)
    rows = db.execute(
        select(DatasetRow.row_number, DatasetRow.values)
        .where(DatasetRow.dataset_id == dataset.id)
        .order_by(DatasetRow.row_number)
    ).all()
    return [(number, values[index] if index < len(values) else "") for number, values in rows]


@dataclass(frozen=True)
class DuplicateReport:
    exact_codes: list[DuplicateGroup]
    leading_zero_suspicions: list[LeadingZeroSuspicion]
    similar_descriptions: list[SimilarPair]


def find_duplicates(
    db: DbSession,
    dataset: Dataset,
    *,
    threshold: float,
    check_descriptions: bool,
) -> DuplicateReport:
    code_items = field_items(db, dataset, "code")
    exact = exact_code_duplicates(code_items)
    suspicions = leading_zero_suspicions(value for _, value in code_items)
    similar: list[SimilarPair] = []
    if check_descriptions:
        desc_items = field_items(db, dataset, "description")
        similar = similar_descriptions(desc_items, threshold=threshold)
    return DuplicateReport(
        exact_codes=exact,
        leading_zero_suspicions=suspicions,
        similar_descriptions=similar,
    )


def compare_datasets(db: DbSession, left: Dataset, right: Dataset) -> CodeComparison:
    left_codes = [value for _, value in field_items(db, left, "code")]
    right_codes = [value for _, value in field_items(db, right, "code")]
    return compare_codes(left_codes, right_codes)
