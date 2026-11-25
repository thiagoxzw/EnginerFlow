"""2B.3 bloco 2: junções (regras puras). Dados sintéticos."""

from __future__ import annotations

import pytest

from engiflow_api.domain import join as jn
from engiflow_api.domain.errors import DomainError

# Esquerda: (A,1) x2, (B,2) x1, chave vazia x1, total 4.
LEFT: Rows = [
    (2, ["A", "1", "x"]),
    (3, ["A", "1", "y"]),
    (4, ["B", "2", "z"]),
    (5, ["C", "", "w"]),
]
# Direita: (A,1) x1, (B,2) x2, (D,3) x1, total 4.
RIGHT: Rows = [
    (2, ["A", "1", "p"]),
    (3, ["B", "2", "q"]),
    (4, ["B", "2", "r"]),
    (5, ["D", "3", "s"]),
]
KEY = (0, 1)

Rows = list[tuple[int, list[str | None]]]


def _plan(left: Rows, right: Rows, t: jn.JoinType) -> jn.JoinPlan:
    lc = jn.count_keys(left, KEY)
    rc = jn.count_keys(right, KEY)
    return jn.plan_join(lc, rc, t)


def test_cardinality_many_to_many_with_counts() -> None:
    plan = _plan(LEFT, RIGHT, "inner")
    assert plan.cardinality == "N:M"
    assert plan.left_keys == 2 and plan.right_keys == 3
    assert plan.matched_keys == 2
    assert plan.max_left_repeat == 2 and plan.max_right_repeat == 2


def test_cardinality_one_to_one_and_one_to_many() -> None:
    one_left: Rows = [(2, ["A", "1", "x"]), (3, ["B", "2", "y"])]
    one_right: Rows = [(2, ["A", "1", "p"]), (3, ["B", "2", "q"]), (4, ["B", "2", "r"])]
    assert _plan(one_left, one_right, "inner").cardinality == "1:N"
    assert _plan(one_right, one_left, "inner").cardinality == "N:1"
    assert (
        _plan(one_left, [(2, ["A", "1", "p"]), (3, ["B", "2", "q"])], "inner").cardinality == "1:1"
    )


@pytest.mark.parametrize(
    ("join_type", "expected"),
    [("inner", 4), ("left", 5), ("right", 5), ("full", 6)],
)
def test_estimated_rows_match_materialized_rows(join_type: jn.JoinType, expected: int) -> None:
    plan = _plan(LEFT, RIGHT, join_type)
    assert plan.estimated_rows == expected
    rows = jn.materialize_join(LEFT, RIGHT, KEY, KEY, 3, 3, join_type, plan)
    assert len(rows) == expected == plan.estimated_rows  # nenhuma multiplicação silenciosa


def test_each_row_carries_its_join_type() -> None:
    plan = _plan(LEFT, RIGHT, "full")
    rows = jn.materialize_join(LEFT, RIGHT, KEY, KEY, 3, 3, "full", plan)
    types = [r[-2] for r in rows]
    assert types.count(jn.TYPE_MATCHED) == 4
    assert types.count(jn.TYPE_LEFT_ONLY) == 1  # chave vazia da esquerda
    assert types.count(jn.TYPE_RIGHT_ONLY) == 1  # D,3 só na direita


def test_refuses_before_materializing_when_estimate_is_too_large() -> None:
    plan = _plan(LEFT, RIGHT, "inner")
    with pytest.raises(DomainError, match="geraria cerca de 4 linhas"):
        jn.check_plan(plan, max_rows=3)
    with pytest.raises(DomainError):
        jn.materialize_join(
            LEFT,
            RIGHT,
            KEY,
            KEY,
            3,
            3,
            "inner",
            jn.JoinPlan(
                join_type="inner",
                cardinality="N:M",
                left_rows=4,
                right_rows=4,
                matched_keys=2,
                left_keys=2,
                right_keys=3,
                left_only_rows=1,
                right_only_rows=1,
                matched_pairs=4,
                estimated_rows=10**9,
                max_left_repeat=2,
                max_right_repeat=2,
            ),
        )


def test_zeros_and_partial_keys_do_not_join() -> None:
    left: Rows = [(2, ["00123", "A", "x"])]
    right: Rows = [(2, ["0123", "A", "p"]), (3, ["00123", "B", "q"])]
    plan = _plan(left, right, "inner")
    assert plan.estimated_rows == 0
    assert plan.matched_keys == 0


def test_invalid_keys_are_unmatched_not_wildcards() -> None:
    left: Rows = [(2, [None, "1", "x"]), (3, ["", "1", "y"])]
    right: Rows = [(2, [None, "1", "p"]), (3, ["", "1", "q"])]
    plan = _plan(left, right, "inner")
    assert plan.estimated_rows == 0
    assert any("inválidas" in note for note in plan.notes)


def test_same_name_columns_get_explicit_suffixes() -> None:
    cols = jn.output_columns(["Código", "Qtd"], ["Código", "Descrição"])
    assert cols == [
        "Código (esquerda)",
        "Qtd",
        "Código (direita)",
        "Descrição",
        "_tipo",
        "_correspondencias",
    ]


def test_full_join_reports_both_sides_without_matches() -> None:
    plan = _plan(LEFT, RIGHT, "full")
    assert plan.left_only_rows == 1
    assert plan.right_only_rows == 1
    assert plan.matched_pairs == 4
