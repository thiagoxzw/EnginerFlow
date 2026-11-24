"""Versionamento de tabelas, metadados e histórico de operações (2B.1 e 2B.2).

Estado de uma tabela = (versão de dados, versão de metadados). As duas cadeias são imutáveis e
são trocadas JUNTAS, numa única atualização condicional (`... WHERE current_version_id = base AND
current_metadata_version_id = base_meta`). Se qualquer um dos ponteiros mudou, é conflito (409).

Garantias:
- Prévia não grava nada. Aplicar exige prévia válida, não usada, com o mesmo estado base.
- Operação só de metadados não copia linhas: cria apenas uma versão de metadados.
- Idempotência: mesma `Idempotency-Key` com a mesma operação devolve o resultado já aplicado.
- Histórico nunca é apagado. Desfazer e refazer movem os dois ponteiros.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application.audit import record_event
from engiflow_api.application.operations.registry import (
    OperationResult,
    OperationSpec,
    Snapshot,
    get_operation,
    validate_params,
)
from engiflow_api.domain.canonical import metadata_sha256, rows_sha256
from engiflow_api.domain.errors import ConflictError, DomainError
from engiflow_api.infrastructure.models import (
    Dataset,
    DatasetMetadataVersion,
    DatasetOperation,
    DatasetPreview,
    DatasetVersion,
    DatasetVersionRow,
)

PREVIEW_TTL = timedelta(minutes=15)
_INSERT_BATCH = 2_000


@dataclass(frozen=True)
class State:
    data_version_id: str
    metadata_version_id: str


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def params_hash(code: str, code_version: int, params: dict[str, Any]) -> str:
    payload = json.dumps(
        {"code": code, "code_version": code_version, "params": params},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_state(db: DbSession, dataset: Dataset) -> State:
    if dataset.current_version_id is None or dataset.current_metadata_version_id is None:
        raise DomainError("Tabela sem versão atual.")
    return State(dataset.current_version_id, dataset.current_metadata_version_id)


def current_version(db: DbSession, dataset: Dataset) -> DatasetVersion:
    version = db.get(DatasetVersion, current_state(db, dataset).data_version_id)
    if version is None:
        raise DomainError("Versão atual não encontrada.")
    return version


def metadata_of(db: DbSession, metadata_version_id: str) -> DatasetMetadataVersion:
    meta = db.get(DatasetMetadataVersion, metadata_version_id)
    if meta is None:
        raise DomainError("Metadados da versão não encontrados.")
    return meta


def load_snapshot(db: DbSession, state: State) -> Snapshot:
    meta = metadata_of(db, state.metadata_version_id)
    rows = db.execute(
        select(DatasetVersionRow.row_number, DatasetVersionRow.values)
        .where(DatasetVersionRow.version_id == state.data_version_id)
        .order_by(DatasetVersionRow.row_number)
    ).all()
    return Snapshot(
        columns=list(meta.columns),
        rows=[list(values) for _, values in rows],
        row_numbers=[number for number, _ in rows],
        mapping=dict(meta.mapping or {}),
        header_row=meta.header_row,
    )


def _resolve_base(
    dataset: Dataset, base_version_id: str, base_metadata_version_id: str | None
) -> State:
    """Estado base informado pelo cliente.

    Sem `base_metadata_version_id` usa os metadados atuais (compatibilidade com a 2B.1).
    """
    if dataset.current_version_id != base_version_id:
        raise ConflictError("A tabela mudou desde a leitura. Atualize a versão e refaça a prévia.")
    if base_metadata_version_id is None:
        if dataset.current_metadata_version_id is None:
            raise DomainError("Tabela sem metadados atuais.")
        return State(base_version_id, dataset.current_metadata_version_id)
    if dataset.current_metadata_version_id != base_metadata_version_id:
        raise ConflictError("Os metadados mudaram desde a leitura. Atualize e refaça a prévia.")
    return State(base_version_id, base_metadata_version_id)


@dataclass(frozen=True)
class ApplyOutcome:
    version: DatasetVersion
    metadata: DatasetMetadataVersion
    operation: DatasetOperation
    created: bool


def create_preview(
    db: DbSession,
    dataset: Dataset,
    *,
    code: str,
    raw_params: dict[str, Any],
    base_version_id: str,
    base_metadata_version_id: str | None = None,
    actor: str,
    correlation_id: str | None,
) -> DatasetPreview:
    base = _resolve_base(dataset, base_version_id, base_metadata_version_id)
    spec: OperationSpec = get_operation(code)
    params = validate_params(spec, raw_params)
    snapshot = load_snapshot(db, base)
    result: OperationResult = spec.apply(snapshot, params)
    rows_hash = (
        rows_sha256(result.snapshot.rows) if spec.touches_data else current_data_hash(db, base)
    )
    meta_hash = metadata_sha256(
        result.snapshot.columns, result.snapshot.mapping, result.snapshot.header_row
    )
    stored = params.model_dump()
    preview = DatasetPreview(
        dataset_id=dataset.id,
        base_version_id=base.data_version_id,
        base_metadata_version_id=base.metadata_version_id,
        code=code,
        code_version=spec.version,
        params=stored,
        params_sha256=params_hash(code, spec.version, stored),
        after_content_sha256=rows_hash,
        after_metadata_sha256=meta_hash,
        rows_affected=result.rows_affected,
        cells_changed=result.cells_changed,
        expires_at=_now() + PREVIEW_TTL,
    )
    db.add(preview)
    db.flush()
    record_event(
        db,
        actor=actor,
        action="data_studio.preview",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={"code": code, "code_version": spec.version, "preview_id": preview.id},
    )
    return preview


def current_data_hash(db: DbSession, state: State) -> str:
    version = db.get(DatasetVersion, state.data_version_id)
    if version is None:
        raise DomainError("Versão de dados não encontrada.")
    return version.content_sha256


def _next_number(db: DbSession, dataset_id: str) -> int:
    value = db.scalar(
        select(func.coalesce(func.max(DatasetVersion.number), 0)).where(
            DatasetVersion.dataset_id == dataset_id
        )
    )
    return int(value or 0) + 1


def _next_metadata_number(db: DbSession, dataset_id: str) -> int:
    value = db.scalar(
        select(func.coalesce(func.max(DatasetMetadataVersion.number), 0)).where(
            DatasetMetadataVersion.dataset_id == dataset_id
        )
    )
    return int(value or 0) + 1


def _next_seq(db: DbSession, dataset_id: str) -> int:
    value = db.scalar(
        select(func.coalesce(func.max(DatasetOperation.seq), 0)).where(
            DatasetOperation.dataset_id == dataset_id
        )
    )
    return int(value or 0) + 1


def _write_data_version(
    db: DbSession, dataset: Dataset, *, parent_id: str, snapshot: Snapshot
) -> DatasetVersion:
    digest = rows_sha256(snapshot.rows)
    version = DatasetVersion(
        id=str(uuid.uuid4()),
        dataset_id=dataset.id,
        number=_next_number(db, dataset.id),
        parent_version_id=parent_id,
        row_count=len(snapshot.rows),
        content_sha256=digest,
        schema_version=2,
        pinned=False,
    )
    db.add(version)
    db.flush()
    for start in range(0, len(snapshot.rows), _INSERT_BATCH):
        db.execute(
            insert(DatasetVersionRow),
            [
                {"version_id": version.id, "row_number": number, "values": values}
                for number, values in zip(
                    snapshot.row_numbers[start : start + _INSERT_BATCH],
                    snapshot.rows[start : start + _INSERT_BATCH],
                    strict=True,
                )
            ],
        )
    return version


def _write_metadata_version(
    db: DbSession,
    dataset: Dataset,
    *,
    data_version_id: str,
    parent_id: str,
    snapshot: Snapshot,
    template_id: str | None = None,
    template_definition_version: int | None = None,
    actor: str = "sistema",
) -> DatasetMetadataVersion:
    meta = DatasetMetadataVersion(
        id=str(uuid.uuid4()),
        dataset_id=dataset.id,
        version_id=data_version_id,
        number=_next_metadata_number(db, dataset.id),
        parent_metadata_version_id=parent_id,
        columns=list(snapshot.columns),
        mapping=dict(snapshot.mapping),
        header_row=snapshot.header_row,
        metadata_sha256=metadata_sha256(snapshot.columns, snapshot.mapping, snapshot.header_row),
        template_id=template_id,
        template_definition_version=template_definition_version,
        actor=actor,
    )
    db.add(meta)
    db.flush()
    return meta


def _move_pointers(
    db: DbSession,
    dataset: Dataset,
    *,
    base: State,
    target: State,
    row_count: int,
    columns: list[str],
    mapping: dict[str, str],
) -> None:
    """Troca os DOIS ponteiros somente se ambos ainda forem a base (atômico)."""
    result = db.execute(
        update(Dataset)
        .where(
            Dataset.id == dataset.id,
            Dataset.current_version_id == base.data_version_id,
            Dataset.current_metadata_version_id == base.metadata_version_id,
        )
        .values(
            current_version_id=target.data_version_id,
            current_metadata_version_id=target.metadata_version_id,
            columns=list(columns),
            mapping=dict(mapping),
            row_count=row_count,
        )
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise ConflictError("A tabela mudou durante a operação. Nada foi alterado.")
    dataset.current_version_id = target.data_version_id
    dataset.current_metadata_version_id = target.metadata_version_id
    dataset.columns = list(columns)
    dataset.mapping = dict(mapping)
    dataset.row_count = row_count


def _mapping_after_move(mapping: dict[str, str], columns: list[str]) -> dict[str, str]:
    """Mapeamento válido para as colunas do destino (usado apenas em tabelas legadas)."""
    return {field: column for field, column in mapping.items() if column in columns}


def apply_preview(
    db: DbSession,
    dataset: Dataset,
    *,
    preview_id: str,
    base_version_id: str,
    base_metadata_version_id: str | None = None,
    idempotency_key: str | None,
    actor: str,
    correlation_id: str | None,
) -> ApplyOutcome:
    if idempotency_key:
        existing = db.scalar(
            select(DatasetOperation).where(
                DatasetOperation.dataset_id == dataset.id,
                DatasetOperation.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            probe = db.get(DatasetPreview, preview_id)
            if (
                probe is not None
                and existing.params_sha256 == probe.params_sha256
                and existing.before_version_id == base_version_id
            ):
                version = db.get(DatasetVersion, existing.after_version_id)
                meta_id = existing.after_metadata_version_id or dataset.current_metadata_version_id
                metadata = db.get(DatasetMetadataVersion, meta_id) if meta_id else None
                if version is None or metadata is None:
                    raise DomainError("Resultado da operação não encontrado.")
                return ApplyOutcome(
                    version=version, metadata=metadata, operation=existing, created=False
                )
            raise ConflictError("Chave de idempotência já usada por outra operação.")

    preview = db.get(DatasetPreview, preview_id)
    if preview is None or preview.dataset_id != dataset.id:
        raise DomainError("Prévia não encontrada para esta tabela.")
    if preview.consumed_at is not None:
        raise ConflictError("Esta prévia já foi aplicada.")
    if _aware(preview.expires_at) <= _now():
        raise DomainError("Prévia expirada. Gere uma nova prévia.")
    base = _resolve_base(dataset, base_version_id, base_metadata_version_id)
    if preview.base_version_id != base.data_version_id or (
        preview.base_metadata_version_id is not None
        and preview.base_metadata_version_id != base.metadata_version_id
    ):
        raise ConflictError("A prévia foi gerada para outro estado. Gere uma nova prévia.")

    consumed = db.execute(
        update(DatasetPreview)
        .where(DatasetPreview.id == preview.id, DatasetPreview.consumed_at.is_(None))
        .values(consumed_at=_now())
    )
    if consumed.rowcount != 1:  # type: ignore[attr-defined]
        raise ConflictError("Esta prévia já foi aplicada.")

    spec = get_operation(preview.code)
    if spec.version != preview.code_version:
        raise ConflictError("Versão da operação mudou desde a prévia. Gere uma nova prévia.")
    params = validate_params(spec, preview.params)
    snapshot = load_snapshot(db, base)
    result = spec.apply(snapshot, params)
    meta_hash = metadata_sha256(
        result.snapshot.columns, result.snapshot.mapping, result.snapshot.header_row
    )
    rows_hash = (
        rows_sha256(result.snapshot.rows) if spec.touches_data else current_data_hash(db, base)
    )
    if rows_hash != preview.after_content_sha256 or meta_hash != preview.after_metadata_sha256:
        raise ConflictError("O resultado divergiu da prévia. Gere uma nova prévia.")

    try:
        if spec.touches_data:
            version = _write_data_version(
                db, dataset, parent_id=base.data_version_id, snapshot=result.snapshot
            )
            data_id = version.id
        else:
            version = db.get(DatasetVersion, base.data_version_id)
            if version is None:
                raise DomainError("Versão de dados não encontrada.")
            data_id = version.id
        meta = _write_metadata_version(
            db,
            dataset,
            data_version_id=data_id,
            parent_id=base.metadata_version_id,
            snapshot=result.snapshot,
        )
        target = State(data_id, meta.id)
        _move_pointers(
            db,
            dataset,
            base=base,
            target=target,
            row_count=version.row_count,
            columns=result.snapshot.columns,
            mapping=result.snapshot.mapping,
        )
    except IntegrityError as exc:  # número de versão ou seq disputado por outro pedido
        raise ConflictError("Operação concorrente detectada. Nada foi alterado.") from exc

    operation = DatasetOperation(
        dataset_id=dataset.id,
        seq=_next_seq(db, dataset.id),
        code=preview.code,
        code_version=spec.version,
        params=preview.params,
        params_sha256=preview.params_sha256,
        status="applied",
        before_version_id=base.data_version_id,
        after_version_id=data_id,
        before_metadata_version_id=base.metadata_version_id,
        after_metadata_version_id=meta.id,
        rows_affected=result.rows_affected,
        cells_changed=result.cells_changed,
        idempotency_key=idempotency_key,
        actor=actor,
    )
    db.add(operation)
    record_event(
        db,
        actor=actor,
        action=f"data_studio.{preview.code}",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={
            "code": preview.code,
            "code_version": spec.version,
            "params_sha256": preview.params_sha256,
            "before_version": base.data_version_id,
            "after_version": data_id,
            "before_metadata": base.metadata_version_id,
            "after_metadata": meta.id,
            "after_content_sha256": rows_hash,
            "after_metadata_sha256": meta_hash,
            "rows_affected": result.rows_affected,
            "cells_changed": result.cells_changed,
        },
    )
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("Operação concorrente detectada. Nada foi alterado.") from exc
    return ApplyOutcome(version=version, metadata=meta, operation=operation, created=True)


def _target_state(db: DbSession, operation: DatasetOperation, direction: str) -> State:
    if direction == "undo":
        data_id, meta_id = operation.before_version_id, operation.before_metadata_version_id
    else:
        data_id, meta_id = operation.after_version_id, operation.after_metadata_version_id
    if (
        meta_id is None
    ):  # operação anterior à 0004: usa a versão de metadados mais recente da versão
        meta = db.scalar(
            select(DatasetMetadataVersion)
            .where(DatasetMetadataVersion.version_id == data_id)
            .order_by(DatasetMetadataVersion.number.desc())
            .limit(1)
        )
        if meta is None:
            raise DomainError("Metadados da versão de destino não encontrados.")
        meta_id = meta.id
    return State(data_id, meta_id)


def _move(
    db: DbSession,
    dataset: Dataset,
    *,
    base_version_id: str,
    base_metadata_version_id: str | None,
    operation: DatasetOperation,
    direction: str,
    actor: str,
    correlation_id: str | None,
) -> State:
    base = _resolve_base(dataset, base_version_id, base_metadata_version_id)
    target = _target_state(db, operation, direction)
    version = db.get(DatasetVersion, target.data_version_id)
    meta = metadata_of(db, target.metadata_version_id)
    if version is None:
        raise DomainError("Versão de destino não encontrada.")
    _move_pointers(
        db,
        dataset,
        base=base,
        target=target,
        row_count=version.row_count,
        columns=list(meta.columns),
        mapping=dict(meta.mapping or {}),
    )
    operation.status = "undone" if direction == "undo" else "applied"
    record_event(
        db,
        actor=actor,
        action=f"data_studio.{direction}",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={
            "operation_id": operation.id,
            "code": operation.code,
            "to_version": target.data_version_id,
        },
    )
    db.flush()
    return target


def undo(
    db: DbSession,
    dataset: Dataset,
    *,
    base_version_id: str,
    base_metadata_version_id: str | None = None,
    actor: str,
    correlation_id: str | None,
) -> State:
    base = _resolve_base(dataset, base_version_id, base_metadata_version_id)
    operation = db.scalar(
        select(DatasetOperation)
        .where(
            DatasetOperation.dataset_id == dataset.id,
            DatasetOperation.status == "applied",
            DatasetOperation.after_version_id == base.data_version_id,
        )
        .order_by(DatasetOperation.seq.desc())
        .limit(1)
    )
    if operation is None:
        raise DomainError("Nada a desfazer nesta tabela.")
    return _move(
        db,
        dataset,
        base_version_id=base.data_version_id,
        base_metadata_version_id=base.metadata_version_id,
        operation=operation,
        direction="undo",
        actor=actor,
        correlation_id=correlation_id,
    )


def redo(
    db: DbSession,
    dataset: Dataset,
    *,
    base_version_id: str,
    base_metadata_version_id: str | None = None,
    actor: str,
    correlation_id: str | None,
) -> State:
    base = _resolve_base(dataset, base_version_id, base_metadata_version_id)
    operation = db.scalar(
        select(DatasetOperation)
        .where(
            DatasetOperation.dataset_id == dataset.id,
            DatasetOperation.status == "undone",
            DatasetOperation.before_version_id == base.data_version_id,
        )
        .order_by(DatasetOperation.seq.desc())
        .limit(1)
    )
    if operation is None:
        raise DomainError("Nada a refazer nesta tabela.")
    return _move(
        db,
        dataset,
        base_version_id=base.data_version_id,
        base_metadata_version_id=base.metadata_version_id,
        operation=operation,
        direction="redo",
        actor=actor,
        correlation_id=correlation_id,
    )


def list_operations(db: DbSession, dataset_id: str) -> list[DatasetOperation]:
    return list(
        db.scalars(
            select(DatasetOperation)
            .where(DatasetOperation.dataset_id == dataset_id)
            .order_by(DatasetOperation.seq)
        ).all()
    )


def list_versions(db: DbSession, dataset_id: str) -> list[DatasetVersion]:
    return list(
        db.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.number)
        ).all()
    )


def list_metadata_versions(db: DbSession, dataset_id: str) -> list[DatasetMetadataVersion]:
    return list(
        db.scalars(
            select(DatasetMetadataVersion)
            .where(DatasetMetadataVersion.dataset_id == dataset_id)
            .order_by(DatasetMetadataVersion.number)
        ).all()
    )
