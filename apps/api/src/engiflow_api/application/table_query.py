"""Consulta paginada de linhas com filtros, pesquisa e ordenação (2B.2, bloco 4).

Sem ordenação: varredura em streaming (lotes) sobre a versão atual; guarda só a página pedida.
Com ordenação: as linhas que casam são materializadas para ordenar. Esse custo é medido na
suíte de desempenho e limitado por `MAX_SORT_ROWS`; acima disso a consulta é recusada.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.query import RowMatcher, TableQuery, sort_index, sort_key
from engiflow_api.infrastructure.models import Dataset, DatasetVersionRow

MAX_SORT_ROWS = 500_000
STREAM_BATCH = 2_000

Page = list[tuple[int, list[str | None]]]


def query_page(
    db: DbSession, dataset: Dataset, query: TableQuery, *, offset: int, limit: int
) -> tuple[int, Page]:
    """Devolve (total de linhas que casam, página de (número da linha, valores))."""
    if dataset.current_version_id is None:
        raise DomainError("Tabela sem versão atual.")
    matcher = RowMatcher(list(dataset.columns), query)
    stmt = (
        select(DatasetVersionRow.row_number, DatasetVersionRow.values)
        .where(DatasetVersionRow.version_id == dataset.current_version_id)
        .order_by(DatasetVersionRow.row_number)
        .execution_options(yield_per=STREAM_BATCH)
    )
    result = db.execute(stmt)

    if query.sort_column is None:
        total = 0
        page: Page = []
        for number, values in result:
            row = list(values)
            if not matcher.matches(row):
                continue
            if offset <= total < offset + limit:
                page.append((number, row))
            total += 1
        return total, page

    index = sort_index(list(dataset.columns), query.sort_column)
    matched: Page = []
    for number, values in result:
        row = list(values)
        if matcher.matches(row):
            matched.append((number, row))
            if len(matched) > MAX_SORT_ROWS:
                raise DomainError(
                    f"Ordenação limitada a {MAX_SORT_ROWS} linhas que casam. "
                    "Adicione filtros antes de ordenar."
                )
    known = [item for item in matched if item[1][index] is not None]
    unknown = [item for item in matched if item[1][index] is None]
    known.sort(
        key=lambda item: (sort_key(item[1][index]), item[0]),
        reverse=query.descending,
    )
    ordered = known + unknown  # desconhecidos sempre por último, em qualquer direção
    return len(ordered), ordered[offset : offset + limit]
