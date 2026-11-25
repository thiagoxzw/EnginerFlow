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
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application.audit import record_event
from engiflow_api.application.versioning import (
    apply_preview,
    create_preview,
    current_state,
)
from engiflow_api.domain.canonical import RowsHasher, metadata_sha256
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
from engiflow_api.infrastructure.models import (
    Dataset,
    DatasetMetadataVersion,
    DatasetVersion,
    DatasetVersionRow,
)
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
            if found.deleted_at is not None:
                raise DomainError(
                    "Este arquivo já foi importado como tabela excluída. Restaure a tabela "
                    "em vez de importar novamente."
                )
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
            # Versão 1 (original). O id da versão é o id da tabela.
            version = DatasetVersion(
                id=dataset.id,
                dataset_id=dataset.id,
                number=1,
                parent_version_id=None,
                row_count=0,
                content_sha256="",
                schema_version=1,
                pinned=True,
            )
            db.add(version)
            db.flush()
            hasher = RowsHasher()
            batch: list[dict[str, Any]] = []
            count = 0
            for number, values in stream.rows:
                hasher.add_row(values)
                batch.append({"version_id": version.id, "row_number": number, "values": values})
                count += 1
                if len(batch) >= INSERT_BATCH_SIZE:
                    db.execute(insert(DatasetVersionRow), batch)
                    batch.clear()
            if batch:
                db.execute(insert(DatasetVersionRow), batch)
            version.row_count = count
            version.content_sha256 = hasher.hexdigest()
            metadata = DatasetMetadataVersion(
                id=str(uuid.uuid4()),
                dataset_id=dataset.id,
                version_id=version.id,
                number=1,
                parent_metadata_version_id=None,
                columns=list(stream.columns),
                mapping={},
                header_row=None,
                metadata_sha256=metadata_sha256(list(stream.columns), {}, None),
                actor=actor,
            )
            db.add(metadata)
            db.flush()
            dataset.current_version_id = version.id
            dataset.current_metadata_version_id = metadata.id
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


def get_dataset(db: DbSession, dataset_id: str, *, include_deleted: bool = False) -> Dataset:
    """Tabela ativa. Tabela excluída logicamente só é acessada com `include_deleted`."""
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise DomainError("Tabela não encontrada.")
    if dataset.deleted_at is not None and not include_deleted:
        raise DomainError("Tabela excluída. Restaure-a para continuar.")
    return dataset


def _ensure_active_name(db: DbSession, name: str, exclude_id: str | None) -> None:
    query = select(Dataset.id).where(
        func.lower(Dataset.name) == name.lower(), Dataset.deleted_at.is_(None)
    )
    if exclude_id is not None:
        query = query.where(Dataset.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise DomainError("Já existe uma tabela ativa com este nome.")


def _clean_name(name: str) -> str:
    clean = " ".join(name.split())
    if not clean or len(clean) > 255:
        raise DomainError("O nome da tabela deve ter entre 1 e 255 caracteres.")
    return clean


def rename_dataset(
    db: DbSession, dataset: Dataset, name: str, *, actor: str, correlation_id: str | None
) -> Dataset:
    clean = _clean_name(name)
    if clean == dataset.name:
        return dataset
    _ensure_active_name(db, clean, exclude_id=dataset.id)
    previous = dataset.name
    dataset.name = clean
    record_event(
        db,
        actor=actor,
        action="dataset.rename",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={"antes": previous, "depois": clean},
    )
    db.flush()
    return dataset


def soft_delete_dataset(
    db: DbSession,
    dataset: Dataset,
    confirm_name: str,
    *,
    actor: str,
    correlation_id: str | None,
) -> Dataset:
    """Exclusão lógica. Exige digitar o nome exato. Nada é apagado do banco."""
    if confirm_name != dataset.name:
        raise DomainError("Confirme digitando o nome exato da tabela para excluir.")
    if dataset.deleted_at is None:
        dataset.deleted_at = datetime.now(UTC)
        record_event(
            db,
            actor=actor,
            action="dataset.delete",
            resource=f"dataset:{dataset.id}",
            result="ok",
            correlation_id=correlation_id,
            details={"nome": dataset.name, "tipo": "exclusão lógica"},
        )
    db.flush()
    return dataset


def restore_dataset(
    db: DbSession, dataset: Dataset, *, actor: str, correlation_id: str | None
) -> Dataset:
    if dataset.deleted_at is None:
        return dataset
    _ensure_active_name(db, dataset.name, exclude_id=dataset.id)
    dataset.deleted_at = None
    record_event(
        db,
        actor=actor,
        action="dataset.restore",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={"nome": dataset.name},
    )
    db.flush()
    return dataset


def set_mapping(
    db: DbSession,
    dataset: Dataset,
    mapping: dict[str, str],
    *,
    actor: str,
    correlation_id: str | None,
) -> Dataset:
    """Mapeamento é uma operação de metadados: gera nova versão de metadados e histórico."""
    clean = validate_mapping(mapping, dataset.columns)
    state = current_state(db, dataset)
    preview = create_preview(
        db,
        dataset,
        code="set_mapping",
        raw_params={"mapping": clean},
        base_version_id=state.data_version_id,
        base_metadata_version_id=state.metadata_version_id,
        actor=actor,
        correlation_id=correlation_id,
    )
    apply_preview(
        db,
        dataset,
        preview_id=preview.id,
        base_version_id=state.data_version_id,
        base_metadata_version_id=state.metadata_version_id,
        idempotency_key=None,
        actor=actor,
        correlation_id=correlation_id,
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


def _current_rows(db: DbSession, dataset: Dataset) -> list[tuple[int, list[str | None]]]:
    if dataset.current_version_id is None:
        raise DomainError("Tabela sem versão atual.")
    rows = db.execute(
        select(DatasetVersionRow.row_number, DatasetVersionRow.values)
        .where(DatasetVersionRow.version_id == dataset.current_version_id)
        .order_by(DatasetVersionRow.row_number)
    ).all()
    return [(number, list(values)) for number, values in rows]


def field_items(db: DbSession, dataset: Dataset, field_name: str) -> list[tuple[int, str]]:
    """Pares (linha na origem, valor) do campo mapeado na versão atual.

    Desconhecido (None) não é código nem descrição: entra como texto vazio na análise e
    não é contado como zero.
    """
    index = _column_index(dataset, field_name)
    return [
        (number, (values[index] or "") if index < len(values) else "")
        for number, values in _current_rows(db, dataset)
    ]


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


def dataset_rows_iter(db: DbSession, dataset: Dataset) -> Iterable[tuple[int, list[str | None]]]:
    """Linhas da versão atual, na ordem da origem (valores None = desconhecido)."""
    return _current_rows(db, dataset)
