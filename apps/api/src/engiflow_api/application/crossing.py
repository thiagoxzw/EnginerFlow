"""Casos de uso de cruzamento entre tabelas (2B.3). Leem apenas as versões atuais; não gravam.

Super-PROCV: a tabela de consulta é lida em streaming; a tabela de busca é indexada em memória
(limitada por `MAX_KEYS`). Linhas de saída são acumuladas até `max_output_rows`; acima disso a
execução é recusada (nunca truncada em silêncio).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application.audit import record_event
from engiflow_api.domain import join as jn
from engiflow_api.domain import lookup as lk
from engiflow_api.domain.canonical import metadata_sha256, rows_sha256
from engiflow_api.domain.errors import DomainError
from engiflow_api.infrastructure.models import (
    CrossingRun,
    CrossingRunSource,
    Dataset,
    DatasetMetadataVersion,
    DatasetVersion,
    DatasetVersionRow,
)

MAX_OUTPUT_ROWS = 500_000
MAX_LEFT_ROWS = 500_000
STREAM_BATCH = 2_000
CONFLICT_SUFFIX = " (direita)"
LOOKUP_OPERATION_VERSION = 1
JOIN_OPERATION_VERSION = 1
_INSERT_BATCH = 2_000


@dataclass(frozen=True)
class LookupSpec:
    left_keys: tuple[str, ...]
    right_keys: tuple[str, ...]
    return_columns: tuple[str, ...]
    policy: lk.LookupPolicy


@dataclass
class LookupOutcome:
    columns: list[str]
    result: lk.LookupResult
    left_rows_read: int


def _indexes(columns: list[str], names: tuple[str, ...], label: str) -> list[int]:
    if not names:
        raise DomainError(f"Informe ao menos uma coluna de chave em {label}.")
    out: list[int] = []
    for name in names:
        if name not in columns:
            raise DomainError(f"Coluna '{name}' não existe em {label}.")
        out.append(columns.index(name))
    if len(set(out)) != len(out):
        raise DomainError(f"Colunas de chave repetidas em {label}.")
    return out


def _stream_current(db: DbSession, dataset: Dataset) -> Any:
    if dataset.current_version_id is None:
        raise DomainError("Tabela sem versão atual.")
    stmt = (
        select(DatasetVersionRow.row_number, DatasetVersionRow.values)
        .where(DatasetVersionRow.version_id == dataset.current_version_id)
        .order_by(DatasetVersionRow.row_number)
        .execution_options(yield_per=STREAM_BATCH)
    )
    return db.execute(stmt)


def output_columns(left: list[str], return_names: list[str]) -> list[str]:
    """Colunas de saída: todas da consulta, depois as retornadas com sufixo se houver conflito."""
    taken = {c.casefold() for c in left}
    out_returns: list[str] = []
    for name in return_names:
        label = name
        if label.casefold() in taken:
            label = f"{name}{CONFLICT_SUFFIX}"
        taken.add(label.casefold())
        out_returns.append(label)
    return [*left, *out_returns, "_status", "_correspondencias"]


def run_lookup(
    db: DbSession,
    left: Dataset,
    right: Dataset,
    spec: LookupSpec,
    *,
    max_output_rows: int | None = None,
) -> LookupOutcome:
    """Executa o Super-PROCV sobre as versões atuais. Recusa acima dos limites."""
    limit = MAX_OUTPUT_ROWS if max_output_rows is None else max_output_rows
    left_cols = list(left.columns)
    right_cols = list(right.columns)
    left_key = _indexes(left_cols, spec.left_keys, "a tabela de consulta")
    right_key = _indexes(right_cols, spec.right_keys, "a tabela de busca")
    if len(spec.left_keys) != len(spec.right_keys):
        raise DomainError("As chaves das duas tabelas devem ter o mesmo número de colunas.")
    return_idx = (
        _indexes(right_cols, spec.return_columns, "a tabela de busca")
        if spec.return_columns
        else []
    )

    right_rows = ((n, list(v)) for n, v in _stream_current(db, right))
    index = lk.build_index(right_rows, right_key, return_idx)

    counted = 0

    def left_rows() -> Any:
        nonlocal counted
        for number, values in _stream_current(db, left):
            counted += 1
            if counted > MAX_LEFT_ROWS:
                raise DomainError(
                    f"A tabela de consulta passa de {MAX_LEFT_ROWS} linhas. Filtre antes de cruzar."
                )
            yield number, list(values)

    result = lk.lookup(left_rows(), index, left_key, len(return_idx), spec.policy, max_rows=limit)
    names = [right_cols[i] for i in return_idx]
    return LookupOutcome(
        columns=output_columns(left_cols, names),
        result=result,
        left_rows_read=counted,
    )


@dataclass(frozen=True)
class DerivedOutcome:
    dataset: Dataset
    run: CrossingRun
    row_count: int
    counts: dict[str, int]


def _canonical_params(spec: LookupSpec, left_id: str, right_id: str) -> dict[str, Any]:
    return {
        "left_id": left_id,
        "right_id": right_id,
        "left_keys": list(spec.left_keys),
        "right_keys": list(spec.right_keys),
        "return_columns": list(spec.return_columns),
        "policy": {"duplicates": spec.policy.duplicates, "unmatched": spec.policy.unmatched},
    }


def store_derived(
    db: DbSession,
    left: Dataset,
    right: Dataset,
    *,
    kind: str,
    operation_version: int,
    label: str,
    params: dict[str, Any],
    counts: dict[str, Any],
    columns: list[str],
    rows: list[list[str | None]],
    actor: str,
    correlation_id: str | None,
) -> DerivedOutcome:
    """Grava o resultado como tabela derivada, com execução e origens congeladas."""
    params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    run = CrossingRun(
        kind=kind,
        operation_version=operation_version,
        params=params,
        params_sha256=hashlib.sha256(params_json.encode("utf-8")).hexdigest(),
        policy=dict(params["policy"]),
        counts=counts,
        result_dataset_id=None,
        result_sha256=rows_sha256(rows),
        row_count=len(rows),
        actor=actor,
    )
    db.add(run)
    db.flush()

    for role, dataset in (("left", left), ("right", right)):
        if dataset.current_version_id is None or dataset.current_metadata_version_id is None:
            raise DomainError("Tabela de origem sem versão atual.")
        db.add(
            CrossingRunSource(
                run_id=run.id,
                role=role,
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                version_id=dataset.current_version_id,
                metadata_version_id=dataset.current_metadata_version_id,
            )
        )

    derived = Dataset(
        name=f"{left.name} × {right.name} ({label})"[:255],
        source_filename="derivada",
        source_sha256=hashlib.sha256(run.id.encode("utf-8")).hexdigest(),
        file_kind="derived",
        sheet_key="",
        sheet_name=None,
        columns=list(columns),
        row_count=len(rows),
        mapping={},
        warnings=[],
        source_kind="derived",
        derived_run_id=run.id,
    )
    db.add(derived)
    db.flush()

    version = DatasetVersion(
        id=derived.id,
        dataset_id=derived.id,
        number=1,
        parent_version_id=None,
        row_count=len(rows),
        content_sha256=run.result_sha256,
        schema_version=2,
        pinned=True,
    )
    db.add(version)
    db.flush()
    for start in range(0, len(rows), _INSERT_BATCH):
        db.execute(
            insert(DatasetVersionRow),
            [
                {"version_id": version.id, "row_number": n, "values": values}
                for n, values in enumerate(rows[start : start + _INSERT_BATCH], start=start + 1)
            ],
        )

    metadata = DatasetMetadataVersion(
        id=str(uuid.uuid4()),
        dataset_id=derived.id,
        version_id=version.id,
        number=1,
        parent_metadata_version_id=None,
        columns=list(columns),
        mapping={},
        header_row=None,
        metadata_sha256=metadata_sha256(columns, {}, None),
        actor=actor,
    )
    db.add(metadata)
    db.flush()
    derived.current_version_id = version.id
    derived.current_metadata_version_id = metadata.id
    run.result_dataset_id = derived.id

    record_event(
        db,
        actor=actor,
        action="crossing.derive",
        resource=f"dataset:{derived.id}",
        result="ok",
        correlation_id=correlation_id,
        details={
            "run_id": run.id,
            "origens": [left.id, right.id],
            "params_sha256": run.params_sha256,
            "result_sha256": run.result_sha256,
            "linhas": len(rows),
            "contagens": counts,
        },
    )
    db.flush()
    return DerivedOutcome(dataset=derived, run=run, row_count=len(rows), counts=counts)


def create_derived_lookup(
    db: DbSession,
    left: Dataset,
    right: Dataset,
    spec: LookupSpec,
    *,
    actor: str,
    correlation_id: str | None,
    max_output_rows: int | None = None,
) -> DerivedOutcome:
    """Executa o Super-PROCV e grava o resultado como tabela derivada, com rastreabilidade."""
    outcome = run_lookup(db, left, right, spec, max_output_rows=max_output_rows)
    rows = [list(values) for _, values in outcome.result.rows]
    params = _canonical_params(spec, left.id, right.id)
    counts = {**outcome.result.counts, "lado_consulta_lido": outcome.left_rows_read}
    return store_derived(
        db,
        left,
        right,
        kind="lookup",
        operation_version=LOOKUP_OPERATION_VERSION,
        label="Super-PROCV",
        params=params,
        counts=counts,
        columns=outcome.columns,
        rows=rows,
        actor=actor,
        correlation_id=correlation_id,
    )


@dataclass
class JoinOutcome:
    columns: list[str]
    rows: list[list[str | None]]
    plan: jn.JoinPlan


def _join_indexes(
    left: Dataset, right: Dataset, left_keys: tuple[str, ...], right_keys: tuple[str, ...]
) -> tuple[list[int], list[int]]:
    if len(left_keys) != len(right_keys):
        raise DomainError("As chaves das duas tabelas devem ter o mesmo número de colunas.")
    return (
        _indexes(list(left.columns), left_keys, "a tabela da esquerda"),
        _indexes(list(right.columns), right_keys, "a tabela da direita"),
    )


def run_join(
    db: DbSession,
    left: Dataset,
    right: Dataset,
    left_keys: tuple[str, ...],
    right_keys: tuple[str, ...],
    join_type: jn.JoinType,
    *,
    max_rows: int | None = None,
) -> JoinOutcome:
    """Calcula cardinalidade e estimativa a partir das contagens; só então materializa."""
    limit = jn.MAX_JOIN_ROWS if max_rows is None else max_rows
    left_idx, right_idx = _join_indexes(left, right, left_keys, right_keys)

    def left_stream() -> Any:
        return ((n, list(v)) for n, v in _stream_current(db, left))

    def right_stream() -> Any:
        return ((n, list(v)) for n, v in _stream_current(db, right))

    plan = jn.plan_join(
        jn.count_keys(left_stream(), left_idx),
        jn.count_keys(right_stream(), right_idx),
        join_type,
    )
    jn.check_plan(plan, max_rows=limit)
    rows = jn.materialize_join(
        left_stream(),
        right_stream(),
        left_idx,
        right_idx,
        len(left.columns),
        len(right.columns),
        join_type,
        plan,
    )
    columns = jn.output_columns(list(left.columns), list(right.columns))
    return JoinOutcome(columns=columns, rows=rows, plan=plan)


def create_derived_join(
    db: DbSession,
    left: Dataset,
    right: Dataset,
    left_keys: tuple[str, ...],
    right_keys: tuple[str, ...],
    join_type: jn.JoinType,
    *,
    actor: str,
    correlation_id: str | None,
    max_rows: int | None = None,
) -> DerivedOutcome:
    """Executa a junção e grava a derivada. Mesma rastreabilidade do Super-PROCV."""
    outcome = run_join(db, left, right, left_keys, right_keys, join_type, max_rows=max_rows)
    plan = outcome.plan
    params: dict[str, Any] = {
        "left_id": left.id,
        "right_id": right.id,
        "left_keys": list(left_keys),
        "right_keys": list(right_keys),
        "policy": {"join_type": join_type},
    }
    counts: dict[str, Any] = {
        "cardinalidade": plan.cardinality,
        "linhas_esquerda": plan.left_rows,
        "linhas_direita": plan.right_rows,
        "chaves_casadas": plan.matched_keys,
        "pares_casados": plan.matched_pairs,
        "so_esquerda": plan.left_only_rows,
        "so_direita": plan.right_only_rows,
        "estimado": plan.estimated_rows,
    }
    return store_derived(
        db,
        left,
        right,
        kind="join",
        operation_version=JOIN_OPERATION_VERSION,
        label=f"Junção {join_type}",
        params=params,
        counts=counts,
        columns=outcome.columns,
        rows=outcome.rows,
        actor=actor,
        correlation_id=correlation_id,
    )
