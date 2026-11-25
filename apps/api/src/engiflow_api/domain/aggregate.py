"""Agrupamento e agregação. Pura, em streaming. Números sempre com Decimal.

Regras:
- Vazio ("") e desconhecido (None) formam grupos próprios e são contados à parte.
- Operações numéricas ignoram vazio e desconhecido; texto que não é número vira "inválido"
  e é contado à parte, sem entrar na soma.
- count = células não vazias e conhecidas; count_distinct = textos canônicos distintos.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from engiflow_api.domain.lookup import canonical_key
from engiflow_api.domain.numeric import format_decimal, parse_decimal

OP_COUNT = "count"
OP_COUNT_DISTINCT = "count_distinct"
OP_SUM = "sum"
OP_AVG = "avg"
OP_MIN = "min"
OP_MAX = "max"
OPERATIONS = (OP_COUNT, OP_COUNT_DISTINCT, OP_SUM, OP_AVG, OP_MIN, OP_MAX)
NUMERIC_OPERATIONS = (OP_SUM, OP_AVG, OP_MIN, OP_MAX)

LABEL_EMPTY = "(vazio)"
LABEL_UNKNOWN = "(desconhecido)"
AVG_PLACES = Decimal("0.0001")

MAX_GROUPS = 50_000


@dataclass
class _Measure:
    column: int
    op: str
    distinct: set[str] = field(default_factory=set)
    count: int = 0
    invalid: int = 0
    total: Decimal = Decimal(0)
    numeric_count: int = 0
    low: Decimal | None = None
    high: Decimal | None = None

    def feed(self, value: str | None) -> None:
        if value is None or value.strip() == "":
            return
        self.count += 1
        if self.op == OP_COUNT:
            return
        if self.op == OP_COUNT_DISTINCT:
            key = canonical_key(value)
            if key is not None:
                self.distinct.add(key)
            return
        number = parse_decimal(value)
        if number is None:
            self.invalid += 1
            return
        self.numeric_count += 1
        self.total += number
        self.low = number if self.low is None or number < self.low else self.low
        self.high = number if self.high is None or number > self.high else self.high

    def result(self) -> str:
        if self.op == OP_COUNT:
            return str(self.count)
        if self.op == OP_COUNT_DISTINCT:
            return str(len(self.distinct))
        if self.op == OP_SUM:
            return format_decimal(self.total) if self.numeric_count else ""
        if self.op == OP_AVG:
            if not self.numeric_count:
                return ""
            average = (self.total / Decimal(self.numeric_count)).quantize(AVG_PLACES, ROUND_HALF_UP)
            return format_decimal(average)
        if self.op == OP_MIN:
            return format_decimal(self.low) if self.low is not None else ""
        if self.op == OP_MAX:
            return format_decimal(self.high) if self.high is not None else ""
        raise ValueError(f"Operação desconhecida: {self.op}")


@dataclass
class AggregateResult:
    columns: list[str]
    rows: list[list[str | None]]
    input_rows: int


def _group_part(value: str | None) -> tuple[str, str]:
    if value is None:
        return ("unknown", LABEL_UNKNOWN)
    if value.strip() == "":
        return ("empty", LABEL_EMPTY)
    return ("value", value.strip())


def aggregate(
    rows: Iterable[Sequence[str | None]],
    group_by: Sequence[int],
    measures: Sequence[tuple[int, str]],
    group_labels: Sequence[str],
    measure_labels: Sequence[str],
    *,
    max_groups: int = MAX_GROUPS,
) -> AggregateResult:
    """Agrupa as linhas e calcula as medidas. Recusa acima de `max_groups` grupos."""
    for _, op in measures:
        if op not in OPERATIONS:
            raise ValueError(f"Operação desconhecida: {op}")

    groups: dict[tuple[tuple[str, str], ...], list[_Measure]] = {}
    sizes: dict[tuple[tuple[str, str], ...], int] = {}
    input_rows = 0
    for values in rows:
        input_rows += 1
        key = tuple(_group_part(values[i]) for i in group_by)
        if key not in groups:
            if len(groups) >= max_groups:
                raise ValueError(
                    f"A agregação passa de {max_groups} grupos. "
                    "Escolha colunas de agrupamento com menos valores."
                )
            groups[key] = [_Measure(column=c, op=op) for c, op in measures]
            sizes[key] = 0
        sizes[key] += 1
        for measure in groups[key]:
            value = values[measure.column] if measure.column < len(values) else None
            measure.feed(value)

    columns = [*group_labels, "linhas"]
    for label, (_, op) in zip(measure_labels, measures, strict=True):
        columns.append(label)
        if op in NUMERIC_OPERATIONS:
            columns.append(f"{label} (inválidos)")

    out: list[list[str | None]] = []
    for key, measure_list in groups.items():
        row: list[Any] = [part[1] for part in key]
        row.append(str(sizes[key]))
        for measure in measure_list:
            row.append(measure.result())
            if measure.op in NUMERIC_OPERATIONS:
                row.append(str(measure.invalid))
        out.append(row)
    return AggregateResult(columns=columns, rows=out, input_rows=input_rows)
