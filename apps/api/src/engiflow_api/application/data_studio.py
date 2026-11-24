"""Casos de uso do Data Studio: importar, mapear, detectar duplicatas, comparar e exportar.

Consistência arquivo x banco (ver docs/operations/FASE_2_STATUS.md):
1. O upload é gravado em arquivo temporário dentro da pasta de armazenamento.
2. As linhas são gravadas em lotes dentro de uma transação (ainda não confirmada).
3. O arquivo temporário é movido para o nome final (hash) só depois de todas as linhas.
4. A transação é confirmada. Se qualquer passo falhar, a transação é desfeita e o arquivo final
   criado por este pedido é removido. Um arquivo que já existia nunca é removido.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
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
from engiflow_api.infrastructure.readers import (
    ImportLimits,
    detect_kind_file,
    open_csv,
    open_xlsx,
)

INSERT_BATCH_SIZE = 2_000
_STALE_TEMP_SECONDS = 3600


@dataclass(frozen=True)
class ImportResult:
    dataset: Dataset
    created: bool


def sweep_stale_temp_files(storage_dir: Path) -> None:
    """Remove temporários deixados por processo interrompido (mais antigos que 1 hora)."""
    if not storage_dir.exists():
        return
    cutoff = time.time() - _STALE_TEMP_SECONDS
    for leftover in storage_dir.glob(".tmp-*"):
        try:
            if leftover.stat().st_mtime < cutoff:
                leftover.unlink()
        except OSError:
            continue


def _existing(db: DbSession, digest: str, sheet_key: str) -> Dataset | None:
    return db.scalar(
        select(Dataset).where(Dataset.source_sha256 == digest, Dataset.sheet_key == sheet_key)
    )


def import_upload(
    db: DbSession,
    *,
    actor: str,
    filename: str,
    temp_path: Path,
    digest: str,
    sheet: str | None,
    limits: ImportLimits,
    storage_dir: Path,
    correlation_id: str | None,
) -> ImportResult:
    sheet_key = sheet or ""
    final_path: Path | None = None
    preexisted = False
    moved = False
    try:
        found = _existing(db, digest, sheet_key)
        if found is not None:
            # Idempotência: mesmo hash e mesma aba não geram registros duplicados.
            return ImportResult(dataset=found, created=False)

        kind = detect_kind_file(temp_path)
        final_path = storage_dir / f"{digest}.{kind}"
        preexisted = final_path.exists()

        ctx = open_csv(temp_path, limits) if kind == "csv" else open_xlsx(temp_path, sheet, limits)
        with ctx as stream:
            dataset = Dataset(
                name=Path(filename).stem[:255] or "Tabela",
                source_filename=Path(filename).name[:255],
                source_sha256=digest,
                file_kind=kind,
                sheet_key=sheet_key,
                sheet_name=stream.sheet,
                columns=stream.columns,
                row_count=0,
                mapping={},
                warnings=[],
            )
            db.add(dataset)
            db.flush()
            batch: list[dict[str, Any]] = []
            count = 0
            for number, values in stream.rows:
                batch.append({"dataset_id": dataset.id, "row_number": number, "values": values})
                count += 1
                if len(batch) >= INSERT_BATCH_SIZE:
                    db.execute(insert(DatasetRow), batch)
                    batch.clear()
            if batch:
                db.execute(insert(DatasetRow), batch)
            dataset.row_count = count
            dataset.warnings = list(stream.warnings)

        storage_dir.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, final_path)
        moved = True
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
                "sheet": dataset.sheet_name,
                "rows": dataset.row_count,
                "columns": len(dataset.columns),
            },
        )
        db.commit()
        return ImportResult(dataset=dataset, created=True)
    except IntegrityError:
        # Outro pedido importou o mesmo arquivo entre a verificação e o commit. O arquivo
        # final, se existe, é o mesmo conteúdo referenciado por esse outro registro: não remover.
        db.rollback()
        found = _existing(db, digest, sheet_key)
        if found is None:
            raise
        return ImportResult(dataset=found, created=False)
    except BaseException:
        db.rollback()
        if moved and not preexisted and final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
    finally:
        temp_path.unlink(missing_ok=True)


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


def dataset_rows_iter(db: DbSession, dataset: Dataset) -> Iterable[tuple[int, list[str]]]:
    """Linhas de uma tabela na ordem da origem, para exportação."""
    result = db.execute(
        select(DatasetRow.row_number, DatasetRow.values)
        .where(DatasetRow.dataset_id == dataset.id)
        .order_by(DatasetRow.row_number)
    )
    for number, values in result:
        yield number, list(values)
