"""Versionamento de tabelas e histórico de operações (2B.1).

Garantias:
- Prévia não altera nada. Aplicar exige prévia válida, não usada, com a mesma versão base.
- Aplicar, desfazer e refazer exigem `base_version_id` igual à versão atual. A troca de versão é
  um UPDATE condicional (`... WHERE current_version_id = base`) na mesma transação; se outro pedido
  mudou a versão primeiro, o resultado é 409 e tudo é desfeito.
- Idempotência: mesma `Idempotency-Key` com a mesma operação retorna o resultado já aplicado.
- Histórico nunca é apagado. Desfazer marca a operação como `undone`.
- Versões não são removidas nesta etapa (retenção será definida por medição, 2B.4).
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
    Snapshot,
    get_operation,
    validate_params,
)
from engiflow_api.domain.canonical import content_sha256
from engiflow_api.domain.errors import ConflictError, DomainError
from engiflow_api.domain.tabular import validate_mapping
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


def current_version(db: DbSession, dataset: Dataset) -> DatasetVersion:
    if dataset.current_version_id is None:
        raise DomainError("Tabela sem versão atual.")
    version = db.get(DatasetVersion, dataset.current_version_id)
    if version is None:
        raise DomainError("Versão atual não encontrada.")
    return version


def load_snapshot(db: DbSession, version_id: str) -> Snapshot:
    meta = db.scalar(
        select(DatasetMetadataVersion).where(DatasetMetadataVersion.version_id == version_id)
    )
    if meta is None:
        raise DomainError("Metadados da versão não encontrados.")
    rows = db.execute(
        select(DatasetVersionRow.row_number, DatasetVersionRow.values)
        .where(DatasetVersionRow.version_id == version_id)
        .order_by(DatasetVersionRow.row_number)
    ).all()
    return Snapshot(
        columns=list(meta.columns),
        rows=[list(values) for _, values in rows],
        row_numbers=[number for number, _ in rows],
    )


def _check_base(dataset: Dataset, base_version_id: str) -> None:
    if dataset.current_version_id != base_version_id:
        raise ConflictError("A tabela mudou desde a leitura. Atualize a versão e refaça a prévia.")


@dataclass(frozen=True)
class ApplyOutcome:
    version: DatasetVersion
    operation: DatasetOperation
    created: bool


def create_preview(
    db: DbSession,
    dataset: Dataset,
    *,
    code: str,
    raw_params: dict[str, Any],
    base_version_id: str,
    actor: str,
    correlation_id: str | None,
) -> DatasetPreview:
    _check_base(dataset, base_version_id)
    spec = get_operation(code)
    params = validate_params(spec, raw_params)
    snapshot = load_snapshot(db, base_version_id)
    result: OperationResult = spec.apply(snapshot, params)
    after = content_sha256(result.snapshot.columns, result.snapshot.rows)
    stored = params.model_dump()
    preview = DatasetPreview(
        dataset_id=dataset.id,
        base_version_id=base_version_id,
        code=code,
        code_version=spec.version,
        params=stored,
        params_sha256=params_hash(code, spec.version, stored),
        after_content_sha256=after,
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


def _next_number(db: DbSession, dataset_id: str) -> int:
    return (
        int(
            db.scalar(
                select(func.coalesce(func.max(DatasetVersion.number), 0)).where(
                    DatasetVersion.dataset_id == dataset_id
                )
            )
            or 0
        )
        + 1
    )


def _next_seq(db: DbSession, dataset_id: str) -> int:
    return (
        int(
            db.scalar(
                select(func.coalesce(func.max(DatasetOperation.seq), 0)).where(
                    DatasetOperation.dataset_id == dataset_id
                )
            )
            or 0
        )
        + 1
    )


def _write_version(
    db: DbSession,
    dataset: Dataset,
    *,
    parent_id: str,
    snapshot: Snapshot,
    mapping: dict[str, str],
    digest: str,
) -> DatasetVersion:
    version = DatasetVersion(
        id=str(uuid.uuid4()),
        dataset_id=dataset.id,
        number=_next_number(db, dataset.id),
        parent_version_id=parent_id,
        row_count=len(snapshot.rows),
        content_sha256=digest,
        schema_version=1,
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
    db.add(
        DatasetMetadataVersion(
            id=str(uuid.uuid4()),
            version_id=version.id,
            columns=list(snapshot.columns),
            mapping=dict(mapping),
        )
    )
    db.flush()
    return version


def _move_pointer(
    db: DbSession,
    dataset: Dataset,
    *,
    base_version_id: str,
    target: DatasetVersion,
    mapping: dict[str, str],
) -> None:
    """Troca a versão atual somente se ainda for a base (guarda de concorrência)."""
    meta = db.scalar(
        select(DatasetMetadataVersion).where(DatasetMetadataVersion.version_id == target.id)
    )
    if meta is None:
        raise DomainError("Metadados da versão de destino não encontrados.")
    result = db.execute(
        update(Dataset)
        .where(Dataset.id == dataset.id, Dataset.current_version_id == base_version_id)
        .values(
            current_version_id=target.id,
            columns=list(meta.columns),
            mapping=dict(mapping),
            row_count=target.row_count,
        )
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise ConflictError("A tabela mudou durante a operação. Nada foi alterado.")
    dataset.current_version_id = target.id
    dataset.columns = list(meta.columns)
    dataset.mapping = dict(mapping)
    dataset.row_count = target.row_count


def _renamed_mapping(mapping: dict[str, str], code: str, params: dict[str, Any]) -> dict[str, str]:
    if code != "rename_column":
        return dict(mapping)
    old, new = params["from_name"], params["to_name"].strip()
    return {field: (new if column == old else column) for field, column in mapping.items()}


def apply_preview(
    db: DbSession,
    dataset: Dataset,
    *,
    preview_id: str,
    base_version_id: str,
    idempotency_key: str | None,
    actor: str,
    correlation_id: str | None,
) -> ApplyOutcome:
    # Idempotência: a mesma chave para a mesma operação devolve o resultado já aplicado.
    if idempotency_key:
        existing = db.scalar(
            select(DatasetOperation).where(
                DatasetOperation.dataset_id == dataset.id,
                DatasetOperation.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            preview_probe = db.get(DatasetPreview, preview_id)
            if (
                preview_probe is not None
                and existing.params_sha256 == preview_probe.params_sha256
                and existing.before_version_id == base_version_id
            ):
                version = db.get(DatasetVersion, existing.after_version_id)
                if version is None:
                    raise DomainError("Versão do resultado não encontrada.")
                return ApplyOutcome(version=version, operation=existing, created=False)
            raise ConflictError("Chave de idempotência já usada por outra operação.")

    preview = db.get(DatasetPreview, preview_id)
    if preview is None or preview.dataset_id != dataset.id:
        raise DomainError("Prévia não encontrada para esta tabela.")
    if preview.consumed_at is not None:
        raise ConflictError("Esta prévia já foi aplicada.")
    if _aware(preview.expires_at) <= _now():
        raise DomainError("Prévia expirada. Gere uma nova prévia.")
    if preview.base_version_id != base_version_id:
        raise ConflictError("A prévia foi gerada para outra versão. Gere uma nova prévia.")
    _check_base(dataset, base_version_id)

    # Consumo único, condicional: só uma aplicação pode marcar a prévia.
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
    snapshot = load_snapshot(db, base_version_id)
    result = spec.apply(snapshot, params)
    digest = content_sha256(result.snapshot.columns, result.snapshot.rows)
    if digest != preview.after_content_sha256:
        raise ConflictError("O resultado divergiu da prévia. Gere uma nova prévia.")

    mapping = _renamed_mapping(
        validate_mapping_safe(dataset.mapping, snapshot.columns), preview.code, preview.params
    )
    mapping = validate_mapping(mapping, result.snapshot.columns)
    try:
        version = _write_version(
            db,
            dataset,
            parent_id=base_version_id,
            snapshot=result.snapshot,
            mapping=mapping,
            digest=digest,
        )
        _move_pointer(db, dataset, base_version_id=base_version_id, target=version, mapping=mapping)
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
        before_version_id=base_version_id,
        after_version_id=version.id,
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
            "before_version": base_version_id,
            "after_version": version.id,
            "after_content_sha256": digest,
            "rows_affected": result.rows_affected,
            "cells_changed": result.cells_changed,
        },
    )
    try:
        db.flush()
    except IntegrityError as exc:  # seq ou chave de idempotência disputadas por outro pedido
        raise ConflictError("Operação concorrente detectada. Nada foi alterado.") from exc
    return ApplyOutcome(version=version, operation=operation, created=True)


def validate_mapping_safe(mapping: dict[str, str], columns: list[str]) -> dict[str, str]:
    """Remove do mapeamento campos cuja coluna não existe mais (ex.: após renomeação)."""
    return {field: column for field, column in mapping.items() if column in columns}


def _mapping_for_move(
    dataset: Dataset, operation: DatasetOperation, direction: str, target_columns: list[str]
) -> dict[str, str]:
    """Mapeamento após desfazer ('undo') ou refazer ('redo').

    O mapeamento é configuração atual da tabela. Desfazer renomeação inverte o nome; refazer
    reaplica. Campos cuja coluna não existe no destino são removidos.
    """
    mapping = dict(dataset.mapping)
    if operation.code == "rename_column":
        old = operation.params["from_name"]
        new = operation.params["to_name"].strip()
        source, target = (new, old) if direction == "undo" else (old, new)
        mapping = {
            field: (target if column == source else column) for field, column in mapping.items()
        }
    return validate_mapping_safe(mapping, target_columns)


def _pointer_guard(
    db: DbSession,
    dataset: Dataset,
    base_version_id: str,
    target: DatasetVersion,
    mapping: dict[str, str],
) -> None:
    """Move o ponteiro para `target` somente se a versão base ainda for a atual."""
    _move_pointer(db, dataset, base_version_id=base_version_id, target=target, mapping=mapping)


def undo(
    db: DbSession,
    dataset: Dataset,
    *,
    base_version_id: str,
    actor: str,
    correlation_id: str | None,
) -> DatasetVersion:
    _check_base(dataset, base_version_id)
    operation = db.scalar(
        select(DatasetOperation)
        .where(
            DatasetOperation.dataset_id == dataset.id,
            DatasetOperation.status == "applied",
            DatasetOperation.after_version_id == base_version_id,
        )
        .order_by(DatasetOperation.seq.desc())
        .limit(1)
    )
    if operation is None:
        raise DomainError("Nada a desfazer nesta tabela.")
    target = db.get(DatasetVersion, operation.before_version_id)
    if target is None:
        raise DomainError("Versão anterior não encontrada.")
    meta = db.scalar(
        select(DatasetMetadataVersion).where(DatasetMetadataVersion.version_id == target.id)
    )
    if meta is None:
        raise DomainError("Metadados da versão de destino não encontrados.")
    mapping = _mapping_for_move(dataset, operation, "undo", list(meta.columns))
    _pointer_guard(db, dataset, base_version_id, target, mapping)
    operation.status = "undone"
    record_event(
        db,
        actor=actor,
        action="data_studio.undo",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={"operation_id": operation.id, "code": operation.code, "to_version": target.id},
    )
    db.flush()
    return target


def redo(
    db: DbSession,
    dataset: Dataset,
    *,
    base_version_id: str,
    actor: str,
    correlation_id: str | None,
) -> DatasetVersion:
    _check_base(dataset, base_version_id)
    operation = db.scalar(
        select(DatasetOperation)
        .where(
            DatasetOperation.dataset_id == dataset.id,
            DatasetOperation.status == "undone",
            DatasetOperation.before_version_id == base_version_id,
        )
        .order_by(DatasetOperation.seq.desc())
        .limit(1)
    )
    if operation is None:
        raise DomainError("Nada a refazer nesta tabela.")
    target = db.get(DatasetVersion, operation.after_version_id)
    if target is None:
        raise DomainError("Versão do resultado não encontrada.")
    meta = db.scalar(
        select(DatasetMetadataVersion).where(DatasetMetadataVersion.version_id == target.id)
    )
    if meta is None:
        raise DomainError("Metadados da versão de destino não encontrados.")
    mapping = _mapping_for_move(dataset, operation, "redo", list(meta.columns))
    _pointer_guard(db, dataset, base_version_id, target, mapping)
    operation.status = "applied"
    record_event(
        db,
        actor=actor,
        action="data_studio.redo",
        resource=f"dataset:{dataset.id}",
        result="ok",
        correlation_id=correlation_id,
        details={"operation_id": operation.id, "code": operation.code, "to_version": target.id},
    )
    db.flush()
    return target


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
