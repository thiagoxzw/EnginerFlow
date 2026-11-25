"""Casos de uso de cruzamento entre tabelas (2B.3). Leem apenas as versões atuais; não gravam.

Super-PROCV: a tabela de consulta é lida em streaming; a tabela de busca é indexada em memória
(limitada por `MAX_KEYS`). Linhas de saída são acumuladas até `max_output_rows`; acima disso a
execução é recusada (nunca truncada em silêncio).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from engiflow_api.domain import lookup as lk
from engiflow_api.domain.errors import DomainError
from engiflow_api.infrastructure.models import Dataset, DatasetVersionRow

MAX_OUTPUT_ROWS = 500_000
MAX_LEFT_ROWS = 500_000
STREAM_BATCH = 2_000
CONFLICT_SUFFIX = " (direita)"


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
