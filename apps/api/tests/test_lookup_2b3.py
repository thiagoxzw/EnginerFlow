"""2B.3 bloco 1: Super-PROCV (regras puras). Dados sintéticos."""

from __future__ import annotations

import pytest

from engiflow_api.domain import lookup as lk
from engiflow_api.domain.errors import DomainError


def _rows(*values: list[str | None]) -> list[tuple[int, list[str | None]]]:
    return [(i + 2, list(v)) for i, v in enumerate(values)]


RIGHT = _rows(
    ["00123", "SYN parafuso", "10"],
    ["0123", "SYN porca", "5"],
    ["AB1", "SYN arruela", "7"],
    ["AB1", "SYN arruela alternativa", "8"],  # chave duplicada
)


def _run(left, policy=None, key_l=(0,), key_r=(0,), ret=(1, 2)):
    policy = policy or lk.LookupPolicy()
    index = lk.build_index(RIGHT, key_r, ret)
    return lk.lookup(left, index, key_l, len(ret), policy)


def test_zeros_are_preserved_and_do_not_match_numerically() -> None:
    result = _run(_rows(["00123", "x"], ["0123", "y"], ["123", "z"]))
    assert result.count(lk.STATUS_FOUND) == 2
    assert result.count(lk.STATUS_NOT_FOUND) == 1
    found = [row for _, row in result.rows if row[-2] == lk.STATUS_FOUND]
    assert found[0][2] == "SYN parafuso"  # 00123 casa com 00123, não com 0123
    assert found[1][2] == "SYN porca"  # 0123 casa com 0123


def test_composite_key_requires_every_part() -> None:
    right = _rows(["A", "1", "desc1"], ["A", "2", "desc2"])
    index = lk.build_index(right, (0, 1), (2,))
    result = lk.lookup(_rows(["A", "2"], ["A", "3"]), index, (0, 1), 1, lk.LookupPolicy())
    assert result.count(lk.STATUS_FOUND) == 1
    assert result.count(lk.STATUS_NOT_FOUND) == 1
    assert result.rows[0][1][2] == "desc2"


def test_unknown_and_empty_keys_never_match() -> None:
    result = _run(_rows([None, "a"], ["", "b"], ["   ", "c"]))
    assert result.count(lk.STATUS_INVALID_KEY) == 3
    assert result.count(lk.STATUS_FOUND) == 0


def test_empty_right_index_still_fills_return_width() -> None:
    index = lk.build_index([], (0,), (1, 2))
    result = lk.lookup(_rows(["X", "a"]), index, (0,), 2, lk.LookupPolicy())
    assert result.rows[0][1] == ["X", "a", None, None, lk.STATUS_NOT_FOUND, "0"]


def test_duplicates_first_keeps_one_row_and_reports_count() -> None:
    result = _run(_rows(["AB1", "q"]), lk.LookupPolicy(duplicates="first"))
    assert len(result.rows) == 1
    assert result.rows[0][1][2] == "SYN arruela"
    assert result.rows[0][1][-2] == lk.STATUS_MULTIPLE
    assert result.rows[0][1][-1] == "2"
    assert result.duplicate_keys == ["AB1"]


def test_duplicates_all_emits_one_row_per_match() -> None:
    result = _run(_rows(["AB1", "q"]), lk.LookupPolicy(duplicates="all"))
    assert len(result.rows) == 2
    assert [row[2] for _, row in result.rows] == ["SYN arruela", "SYN arruela alternativa"]


def test_duplicates_error_refuses_with_guidance() -> None:
    with pytest.raises(DomainError, match="múltiplas correspondências"):
        _run(_rows(["AB1", "q"]), lk.LookupPolicy(duplicates="error"))


def test_drop_unmatched_removes_rows_but_counts_them() -> None:
    result = _run(_rows(["00123", "a"], ["NOPE", "b"]), lk.LookupPolicy(unmatched="drop"))
    assert len(result.rows) == 1
    assert result.count(lk.STATUS_NOT_FOUND) == 1
    assert result.unmatched_keys == ["NOPE"]


def test_every_input_row_is_accounted_for_in_counts() -> None:
    left = _rows(["00123", "a"], ["AB1", "b"], ["ZZZ", "c"], [None, "d"])
    result = _run(left, lk.LookupPolicy(duplicates="first"))
    assert sum(result.counts.values()) == len(left)


def test_canonical_key_normalizes_unicode_but_not_zeros() -> None:
    decomposed = "ÁB"  # "Á" decomposto
    assert lk.canonical_key(decomposed) == lk.canonical_key("ÁB")
    assert lk.canonical_key("00123") == "00123"


def test_index_respects_distinct_key_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lk, "MAX_KEYS", 2)
    right = _rows(["1", "a"], ["2", "b"], ["3", "c"])
    with pytest.raises(DomainError, match="chaves distintas"):
        lk.build_index(right, (0,), (1,))


def test_invalid_policy_values_are_rejected() -> None:
    with pytest.raises(DomainError):
        lk.LookupPolicy(duplicates="maybe")  # type: ignore[arg-type]
