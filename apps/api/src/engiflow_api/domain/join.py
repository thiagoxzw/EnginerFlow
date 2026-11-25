"""Junções entre tabelas (2B.3): INNER, LEFT, RIGHT e FULL OUTER, com chaves compostas.

Ordem de execução (sem multiplicação silenciosa):
1. `count_keys` conta chaves canônicas de cada lado (streaming, uma passagem por tabela).
2. `plan_join` calcula cardinalidade (1:1, 1:N, N:1, N:M) e linhas estimadas a partir das
   contagens. Nada é materializado aqui.
3. `materialize_join` só roda se a estimativa couber no limite; senão recusa.

Chaves com valor desconhecido ou vazio nunca casam; em LEFT/RIGHT/FULL aparecem como registros
sem correspondência. Colunas com o mesmo nome nos dois lados recebem sufixos explícitos.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.lookup import composite_key

JoinType = Literal["inner", "left", "right", "full"]
JOIN_TYPES: tuple[JoinType, ...] = ("inner", "left", "right", "full")

MAX_JOIN_ROWS = 500_000
MAX_KEYS = 500_000
LEFT_SUFFIX = " (esquerda)"
RIGHT_SUFFIX = " (direita)"

TYPE_MATCHED = "casado"
TYPE_LEFT_ONLY = "só esquerda"
TYPE_RIGHT_ONLY = "só direita"


@dataclass(frozen=True)
class KeyCounts:
    """Contagem de linhas por chave canônica e de linhas sem chave válida."""

    by_key: Counter[tuple[str, ...]]
    invalid: int
    total: int


@dataclass(frozen=True)
class JoinPlan:
    join_type: JoinType
    cardinality: str
    left_rows: int
    right_rows: int
    matched_keys: int
    left_keys: int
    right_keys: int
    left_only_rows: int
    right_only_rows: int
    matched_pairs: int
    estimated_rows: int
    max_left_repeat: int
    max_right_repeat: int
    notes: list[str] = field(default_factory=list)


def count_keys(rows: Iterable[tuple[int, list[str | None]]], key: Sequence[int]) -> KeyCounts:
    counts: Counter[tuple[str, ...]] = Counter()
    invalid = 0
    total = 0
    for _number, values in rows:
        total += 1
        k = composite_key(values, key)
        if k is None:
            invalid += 1
            continue
        if k not in counts and len(counts) >= MAX_KEYS:
            raise DomainError(
                f"Mais de {MAX_KEYS} chaves distintas. Reduza as tabelas antes de cruzar."
            )
        counts[k] += 1
    return KeyCounts(by_key=counts, invalid=invalid, total=total)


def _cardinality(left_max: int, right_max: int) -> str:
    if left_max <= 1 and right_max <= 1:
        return "1:1"
    if left_max <= 1:
        return "1:N"
    if right_max <= 1:
        return "N:1"
    return "N:M"


def plan_join(left: KeyCounts, right: KeyCounts, join_type: JoinType) -> JoinPlan:
    """Cardinalidade e linhas estimadas a partir das contagens. Não lê linhas."""
    if join_type not in JOIN_TYPES:
        raise DomainError("Tipo de junção inválido.")
    common = set(left.by_key) & set(right.by_key)
    matched_pairs = sum(left.by_key[k] * right.by_key[k] for k in common)
    matched_left = sum(left.by_key[k] for k in common)
    matched_right = sum(right.by_key[k] for k in common)
    left_only = left.total - matched_left
    right_only = right.total - matched_right

    if join_type == "inner":
        estimated = matched_pairs
    elif join_type == "left":
        estimated = matched_pairs + left_only
    elif join_type == "right":
        estimated = matched_pairs + right_only
    else:
        estimated = matched_pairs + left_only + right_only

    left_max = max(left.by_key.values(), default=0)
    right_max = max(right.by_key.values(), default=0)
    notes: list[str] = []
    cardinality = _cardinality(left_max, right_max)
    if cardinality == "N:M":
        notes.append(
            "Relação muitos para muitos: cada chave repetida gera o produto das ocorrências."
        )
    if left.invalid or right.invalid:
        notes.append(
            f"Chaves inválidas (vazias ou desconhecidas) nunca casam: "
            f"{left.invalid} na esquerda e {right.invalid} na direita."
        )
    return JoinPlan(
        join_type=join_type,
        cardinality=cardinality,
        left_rows=left.total,
        right_rows=right.total,
        matched_keys=len(common),
        left_keys=len(left.by_key),
        right_keys=len(right.by_key),
        left_only_rows=left_only,
        right_only_rows=right_only,
        matched_pairs=matched_pairs,
        estimated_rows=estimated,
        max_left_repeat=left_max,
        max_right_repeat=right_max,
        notes=notes,
    )


def check_plan(plan: JoinPlan, max_rows: int = MAX_JOIN_ROWS) -> None:
    """Recusa antes de materializar se a estimativa passar do limite."""
    if plan.estimated_rows > max_rows:
        raise DomainError(
            f"A junção geraria cerca de {plan.estimated_rows} linhas (limite {max_rows}). "
            "Filtre as tabelas ou revise a relação entre as chaves."
        )


def output_columns(left: list[str], right: list[str]) -> list[str]:
    """Colunas da junção: nomes repetidos nos dois lados recebem sufixos explícitos."""
    left_names = {c.casefold() for c in right}
    right_names = {c.casefold() for c in left}
    out = [(c + LEFT_SUFFIX) if c.casefold() in left_names else c for c in left]
    out += [(c + RIGHT_SUFFIX) if c.casefold() in right_names else c for c in right]
    return [*out, "_tipo", "_correspondencias"]


def materialize_join(
    left_rows: Iterable[tuple[int, list[str | None]]],
    right_rows: Iterable[tuple[int, list[str | None]]],
    left_key: Sequence[int],
    right_key: Sequence[int],
    left_width: int,
    right_width: int,
    join_type: JoinType,
    plan: JoinPlan,
) -> list[list[str | None]]:
    """Materializa a junção. Use somente depois de `check_plan`."""
    check_plan(plan)
    index: dict[tuple[str, ...], list[list[str | None]]] = {}
    matched_right_keys: set[tuple[str, ...]] = set()
    right_list: list[tuple[tuple[str, ...] | None, list[str | None]]] = []
    for _number, values in right_rows:
        k = composite_key(values, right_key)
        right_list.append((k, values))
        if k is not None:
            index.setdefault(k, []).append(values)

    blank_left: list[str | None] = [None] * left_width
    blank_right: list[str | None] = [None] * right_width
    out: list[list[str | None]] = []
    for _number, lvalues in left_rows:
        k = composite_key(lvalues, left_key)
        partners = index.get(k, []) if k is not None else []
        if partners:
            if k is not None:
                matched_right_keys.add(k)
            for rvalues in partners:
                out.append([*lvalues, *rvalues, TYPE_MATCHED, str(len(partners))])
        elif join_type in ("left", "full"):
            out.append([*lvalues, *blank_right, TYPE_LEFT_ONLY, "0"])
    if join_type in ("right", "full"):
        for k, rvalues in right_list:
            if k is None or k not in matched_right_keys:
                out.append([*blank_left, *rvalues, TYPE_RIGHT_ONLY, "0"])
    return out
