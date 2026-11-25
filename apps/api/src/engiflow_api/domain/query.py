"""Regras puras de filtro, pesquisa e ordenação de linhas (2B.2, bloco 4).

Estados de uma célula (nunca convertidos no armazenamento):
- desconhecido = None: não casa com filtros de texto ou numéricos; só com `is_unknown`.
- vazio = "": casa com `is_empty`.
- zero = "0": casa com `is_zero` e comparações numéricas (é um número válido).

Ordenação: linhas conhecidas primeiro (numéricas antes de textuais, pela ordem escolhida);
desconhecidos sempre por último, em qualquer direção. Desempate pelo número da linha.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engiflow_api.domain.errors import DomainError

MAX_FILTERS = 20
MAX_SEARCH = 200

FilterOp = Literal[
    "eq",
    "neq",
    "contains",
    "starts",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "is_empty",
    "not_empty",
    "is_unknown",
    "not_unknown",
    "is_zero",
    "not_zero",
]
Predicate = Callable[[str | None], bool]

_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")


class FilterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1, max_length=255)
    op: FilterOp
    value: str | None = Field(default=None, max_length=1000)
    value2: str | None = Field(default=None, max_length=1000)


@dataclass(frozen=True)
class TableQuery:
    filters: list[FilterIn] = field(default_factory=list)
    search: str = ""
    sort_column: str | None = None
    descending: bool = False

    def is_plain(self) -> bool:
        return not self.filters and not self.search and self.sort_column is None


def fold(text: str) -> str:
    """Minúsculas e sem acentos (para pesquisa tolerante). Não altera o valor armazenado."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def parse_number(text: str | None) -> Decimal | None:
    """Interpreta número para FILTRO e ORDENAÇÃO apenas. Aceita vírgula decimal.

    Valor armazenado nunca é reescrito. Texto que não é número retorna None.
    """
    if text is None:
        return None
    value = text.strip()
    if "," in value and "." not in value:
        value = value.replace(",", ".")
    if not _NUMBER.match(value):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _column_index(columns: list[str], name: str) -> int:
    try:
        return columns.index(name)
    except ValueError as exc:
        raise DomainError(f"Coluna '{name}' não existe nesta tabela.") from exc


def _number_arg(raw: str | None, label: str) -> Decimal:
    number = parse_number(raw)
    if number is None:
        raise DomainError(f"Valor numérico inválido em {label}: '{raw}'.")
    return number


def compile_filter(columns: list[str], flt: FilterIn) -> tuple[int, Predicate]:
    """Valida o filtro e devolve (índice da coluna, predicado sobre o valor da célula)."""
    index = _column_index(columns, flt.column)
    op = flt.op
    if op == "is_unknown":
        return index, lambda cell: cell is None
    if op == "not_unknown":
        return index, lambda cell: cell is not None
    if op == "is_empty":
        return index, lambda cell: cell == ""
    if op == "not_empty":
        return index, lambda cell: cell is not None and cell != ""
    if op == "is_zero":
        return index, lambda cell: parse_number(cell) == 0 if cell is not None else False
    if op == "not_zero":
        return index, lambda cell: (cell is not None) and parse_number(cell) != 0

    if op in ("eq", "neq", "contains", "starts"):
        if flt.value is None:
            raise DomainError(f"Filtro '{op}' exige um valor.")
        needle = flt.value
        if op == "eq":
            return index, lambda cell: cell is not None and cell == needle
        if op == "neq":
            return index, lambda cell: cell is not None and cell != needle
        folded = fold(needle)
        if op == "contains":
            return index, lambda cell: cell is not None and folded in fold(cell)
        return index, lambda cell: cell is not None and fold(cell).startswith(folded)

    # numéricos: célula desconhecida ou não numérica nunca casa
    if op == "between":
        low = _number_arg(flt.value, "entre (mínimo)")
        high = _number_arg(flt.value2, "entre (máximo)")
        if low > high:
            raise DomainError("Em 'entre', o mínimo deve ser menor ou igual ao máximo.")

        def between(cell: str | None) -> bool:
            number = parse_number(cell)
            return number is not None and low <= number <= high

        return index, between

    bound = _number_arg(flt.value, op)
    comparators: dict[str, Callable[[Decimal], bool]] = {
        "gt": lambda n: n > bound,
        "gte": lambda n: n >= bound,
        "lt": lambda n: n < bound,
        "lte": lambda n: n <= bound,
    }
    compare = comparators[op]

    def numeric(cell: str | None) -> bool:
        number = parse_number(cell)
        return number is not None and compare(number)

    return index, numeric


class RowMatcher:
    """Aplica filtros combinados (E) e a pesquisa global sobre uma linha."""

    def __init__(self, columns: list[str], query: TableQuery) -> None:
        if len(query.filters) > MAX_FILTERS:
            raise DomainError(f"No máximo {MAX_FILTERS} filtros por consulta.")
        if len(query.search) > MAX_SEARCH:
            raise DomainError(f"Pesquisa com no máximo {MAX_SEARCH} caracteres.")
        self._predicates = [compile_filter(columns, f) for f in query.filters]
        self._needle = fold(query.search.strip()) if query.search.strip() else ""

    def matches(self, values: list[str | None]) -> bool:
        for index, predicate in self._predicates:
            if not predicate(values[index]):
                return False
        if self._needle:
            return any(cell is not None and self._needle in fold(cell) for cell in values)
        return True


def sort_index(columns: list[str], name: str) -> int:
    return _column_index(columns, name)


def sort_key(cell: str | None) -> tuple[int, Decimal | str]:
    """Chave de ordenação para uma célula conhecida (desconhecidos tratados à parte)."""
    number = parse_number(cell)
    if number is not None:
        return (0, number)
    return (1, fold(cell or ""))
