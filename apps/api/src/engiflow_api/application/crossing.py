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
from engiflow_api.domain import aggregate as ag
from engiflow_api.domain import comparison as cmp_mod
from engiflow_api.domain import formula as fm
from engiflow_api.domain import join as jn
from engiflow_api.domain import lookup as lk
from engiflow_api.domain.canonical import metadata_sha256, rows_sha256
from engiflow_api.domain.errors import ConflictError, DomainError
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


def _params_sha(params: dict[str, Any]) -> str:
    params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(params_json.encode("utf-8")).hexdigest()


def replay_derived(
    db: DbSession, idempotency_key: str | None, kind: str, params: dict[str, Any]
) -> DerivedOutcome | None:
    """Repete o resultado de uma execução anterior com a mesma chave de idempotência.

    - Sem chave: nada a repetir (None).
    - Mesma chave e mesmos parâmetros: devolve a execução já gravada, sem recalcular nem duplicar.
    - Mesma chave com parâmetros (ou operação) diferentes: conflito (409).
    """
    if not idempotency_key:
        return None
    run = db.scalar(select(CrossingRun).where(CrossingRun.idempotency_key == idempotency_key))
    if run is None:
        return None
    if run.kind != kind or run.params_sha256 != _params_sha(params):
        raise ConflictError(
            "A chave de idempotência já foi usada com outros parâmetros. Use uma chave nova."
        )
    dataset = db.get(Dataset, run.result_dataset_id) if run.result_dataset_id else None
    if dataset is None:
        raise ConflictError("A execução anterior não tem tabela derivada. Use uma chave nova.")
    return DerivedOutcome(
        dataset=dataset, run=run, row_count=run.row_count, counts=dict(run.counts)
    )


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
    right: Dataset | None,
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
    idempotency_key: str | None = None,
) -> DerivedOutcome:
    """Grava o resultado como tabela derivada, com execução e origens congeladas."""
    run = CrossingRun(
        kind=kind,
        operation_version=operation_version,
        params=params,
        params_sha256=_params_sha(params),
        idempotency_key=idempotency_key,
        policy=dict(params["policy"]),
        counts=counts,
        result_dataset_id=None,
        result_sha256=rows_sha256(rows),
        row_count=len(rows),
        actor=actor,
    )
    db.add(run)
    db.flush()

    sources = [("left", left)] + ([("right", right)] if right is not None else [])
    for role, dataset in sources:
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

    origin_name = left.name if right is None else f"{left.name} × {right.name}"
    derived = Dataset(
        name=f"{origin_name} ({label})"[:255],
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
            "origens": [dataset.id for _, dataset in sources],
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
    idempotency_key: str | None = None,
) -> DerivedOutcome:
    """Executa o Super-PROCV e grava o resultado como tabela derivada, com rastreabilidade."""
    params = _canonical_params(spec, left.id, right.id)
    replayed = replay_derived(db, idempotency_key, "lookup", params)
    if replayed is not None:
        return replayed
    outcome = run_lookup(db, left, right, spec, max_output_rows=max_output_rows)
    rows = [list(values) for _, values in outcome.result.rows]
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
        idempotency_key=idempotency_key,
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
    idempotency_key: str | None = None,
) -> DerivedOutcome:
    """Executa a junção e grava a derivada. Mesma rastreabilidade do Super-PROCV."""
    params: dict[str, Any] = {
        "left_id": left.id,
        "right_id": right.id,
        "left_keys": list(left_keys),
        "right_keys": list(right_keys),
        "policy": {"join_type": join_type},
    }
    replayed = replay_derived(db, idempotency_key, "join", params)
    if replayed is not None:
        return replayed
    outcome = run_join(db, left, right, left_keys, right_keys, join_type, max_rows=max_rows)
    plan = outcome.plan
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
        idempotency_key=idempotency_key,
    )


AGGREGATE_OPERATION_VERSION = 1

MEASURE_LABELS = {
    "count": "contagem",
    "count_distinct": "distintos",
    "sum": "soma",
    "avg": "média",
    "min": "mínimo",
    "max": "máximo",
}


@dataclass(frozen=True)
class AggregateSpec:
    group_by: tuple[str, ...]
    measures: tuple[tuple[str, str], ...]


def _aggregate_plan(
    dataset: Dataset, spec: AggregateSpec
) -> tuple[list[int], list[tuple[int, str]], list[str]]:
    columns = list(dataset.columns)
    group_idx = _indexes(columns, spec.group_by, "a tabela") if spec.group_by else []
    measure_idx: list[tuple[int, str]] = []
    labels: list[str] = []
    for name, op in spec.measures:
        if op not in ag.OPERATIONS:
            raise DomainError(f"Operação de agregação desconhecida: '{op}'.")
        measure_idx.append((_indexes(columns, (name,), "a tabela")[0], op))
        labels.append(f"{MEASURE_LABELS[op]} de {name}")
    return group_idx, measure_idx, labels


def run_aggregate(
    db: DbSession, dataset: Dataset, spec: AggregateSpec, *, max_groups: int = ag.MAX_GROUPS
) -> ag.AggregateResult:
    """Agrega a versão atual da tabela. Recusa acima do limite de grupos."""
    group_idx, measure_idx, labels = _aggregate_plan(dataset, spec)
    columns = list(dataset.columns)
    rows = (list(values) for _, values in _stream_current(db, dataset))
    try:
        return ag.aggregate(
            rows,
            group_idx,
            measure_idx,
            [columns[i] for i in group_idx],
            labels,
            max_groups=max_groups,
        )
    except ValueError as exc:
        raise DomainError(str(exc)) from exc


def create_derived_aggregate(
    db: DbSession,
    dataset: Dataset,
    spec: AggregateSpec,
    *,
    actor: str,
    correlation_id: str | None,
    idempotency_key: str | None = None,
) -> DerivedOutcome:
    params: dict[str, Any] = {
        "dataset_id": dataset.id,
        "group_by": list(spec.group_by),
        "measures": [[name, op] for name, op in spec.measures],
        "policy": {"operation": "aggregate"},
    }
    replayed = replay_derived(db, idempotency_key, "aggregate", params)
    if replayed is not None:
        return replayed
    result = run_aggregate(db, dataset, spec)
    counts: dict[str, Any] = {"linhas_lidas": result.input_rows, "grupos": len(result.rows)}
    return store_derived(
        db,
        dataset,
        None,
        kind="aggregate",
        operation_version=AGGREGATE_OPERATION_VERSION,
        label="Agregação",
        params=params,
        counts=counts,
        columns=result.columns,
        rows=result.rows,
        actor=actor,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )


COMPARISON_OPERATION_VERSION = 1


@dataclass(frozen=True)
class ComparisonSpec:
    left_keys: tuple[str, ...]
    right_keys: tuple[str, ...]
    # Modo por coluna comparada (nome, modo). Colunas não citadas usam "exato".
    modes: tuple[tuple[str, str], ...] = ()


def _shared_columns(
    left_cols: list[str], right_cols: list[str], left_key: list[int], right_key: list[int]
) -> list[tuple[int, int, str]]:
    """Colunas com o mesmo nome (sem diferenciar maiúsculas) que não são chave."""
    right_map = {c.casefold(): j for j, c in enumerate(right_cols)}
    out: list[tuple[int, int, str]] = []
    for i, name in enumerate(left_cols):
        if i in left_key:
            continue
        j = right_map.get(name.casefold())
        if j is None or j in right_key:
            continue
        out.append((i, j, name))
    return out


def _comparison_plan(
    left: Dataset, right: Dataset, spec: ComparisonSpec
) -> tuple[list[int], list[int], list[tuple[int, int, str]], dict[str, str]]:
    """Índices das chaves, colunas comparadas e modo de cada uma (valida nomes e modos)."""
    left_cols = list(left.columns)
    right_cols = list(right.columns)
    left_key = _indexes(left_cols, spec.left_keys, "a tabela de origem")
    right_key = _indexes(right_cols, spec.right_keys, "a tabela de comparação")
    if len(left_key) != len(right_key):
        raise DomainError("As chaves das duas tabelas devem ter o mesmo número de colunas.")
    shared = _shared_columns(left_cols, right_cols, left_key, right_key)
    shared_names = {name.casefold(): name for _, _, name in shared}
    modes = {name: cmp_mod.MODE_EXACT for _, _, name in shared}
    for column, mode in spec.modes:
        canonical = shared_names.get(column.casefold())
        if canonical is None:
            raise DomainError(
                f"A coluna '{column}' não é comparada (existe nas duas tabelas e não é chave)."
            )
        if mode not in cmp_mod.MODES:
            raise DomainError(f"Modo de comparação desconhecido: '{mode}'.")
        modes[canonical] = mode
    return left_key, right_key, shared, modes


def run_comparison(
    db: DbSession, left: Dataset, right: Dataset, spec: ComparisonSpec
) -> cmp_mod.ComparisonResult:
    left_key, right_key, shared, modes = _comparison_plan(left, right, spec)
    left_rows = (list(values) for _, values in _stream_current(db, left))
    right_rows = (list(values) for _, values in _stream_current(db, right))
    try:
        return cmp_mod.compare(left_rows, right_rows, left_key, right_key, shared, modes=modes)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc


def create_derived_comparison(
    db: DbSession,
    left: Dataset,
    right: Dataset,
    spec: ComparisonSpec,
    *,
    actor: str,
    correlation_id: str | None,
    idempotency_key: str | None = None,
) -> DerivedOutcome:
    _, _, _, modes = _comparison_plan(left, right, spec)
    params: dict[str, Any] = {
        "left_id": left.id,
        "right_id": right.id,
        "left_keys": list(spec.left_keys),
        "right_keys": list(spec.right_keys),
        # Chaves: sempre texto canônico, sem equivalência numérica.
        "chaves": "texto canônico (NFC, sem alterar zeros, caixa ou símbolos)",
        # Modo efetivo de cada coluna comparada, para rastrear exatamente o critério usado.
        "modos": dict(sorted(modes.items())),
        "policy": {"operation": "compare", "modos": dict(sorted(modes.items()))},
    }
    replayed = replay_derived(db, idempotency_key, "compare", params)
    if replayed is not None:
        return replayed
    result = run_comparison(db, left, right, spec)
    return store_derived(
        db,
        left,
        right,
        kind="compare",
        operation_version=COMPARISON_OPERATION_VERSION,
        label="Comparação por chave",
        params=params,
        counts=dict(result.counts),
        columns=result.columns,
        rows=result.rows,
        actor=actor,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )


FORMULA_OPERATION_VERSION = 1


@dataclass(frozen=True)
class FormulaSpec:
    formula: str
    new_column: str


def _formula_plan(dataset: Dataset, spec: FormulaSpec) -> fm.Formula:
    columns = list(dataset.columns)
    name = spec.new_column.strip()
    if not name or len(name) > 255:
        raise DomainError("Informe o nome da nova coluna (até 255 caracteres).")
    if name.casefold() in {c.casefold() for c in columns}:
        raise DomainError(f"Já existe uma coluna chamada '{name}'.")
    try:
        return fm.compile_formula(spec.formula, columns)
    except fm.FormulaError as exc:
        raise DomainError(str(exc)) from exc


def run_formula(
    db: DbSession, dataset: Dataset, spec: FormulaSpec
) -> tuple[list[str], list[list[str | None]], dict[str, Any]]:
    """Calcula a fórmula em cada linha da versão atual. Erros ficam explícitos na célula."""
    formula = _formula_plan(dataset, spec)
    columns = [*dataset.columns, spec.new_column.strip()]
    names = list(dataset.columns)
    rows: list[list[str | None]] = []
    errors = 0
    read = 0
    for _, values in _stream_current(db, dataset):
        read += 1
        text = fm.evaluate_row(formula, dict(zip(names, values, strict=True)))
        if fm.is_error_text(text):
            errors += 1
        rows.append([*values, text])
    return columns, rows, {"linhas_lidas": read, "erros": errors}


def create_derived_formula(
    db: DbSession,
    dataset: Dataset,
    spec: FormulaSpec,
    *,
    actor: str,
    correlation_id: str | None,
    idempotency_key: str | None = None,
) -> DerivedOutcome:
    _formula_plan(dataset, spec)  # valida antes de qualquer leitura de linhas
    params: dict[str, Any] = {
        "dataset_id": dataset.id,
        "formula": spec.formula,
        "nova_coluna": spec.new_column.strip(),
        "policy": {"operation": "formula", "erros_na_celula": "explícitos (#VAZIO!, #DIV/0!...)"},
    }
    replayed = replay_derived(db, idempotency_key, "formula", params)
    if replayed is not None:
        return replayed
    columns, rows, counts = run_formula(db, dataset, spec)
    return store_derived(
        db,
        dataset,
        None,
        kind="formula",
        operation_version=FORMULA_OPERATION_VERSION,
        label="Fórmula",
        params=params,
        counts=counts,
        columns=columns,
        rows=rows,
        actor=actor,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
