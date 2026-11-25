"""2B.3: números com Decimal, agrupamento e agregação. Dados sintéticos."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings
from engiflow_api.domain import aggregate as ag
from engiflow_api.domain.numeric import format_decimal, parse_decimal

AGRUPADO = b"SYN-Grupo;SYN-Valor\nA;1.234,50\nA;10\nA;abc\nB;2,5\nB;\nC;-3,25\n"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("1234,5", Decimal("1234.5")),
        ("1234.5", Decimal("1234.5")),
        ("-0,5", Decimal("-0.5")),
        ("1000", Decimal("1000")),
        ("  7  ", Decimal("7")),
    ],
)
def test_parse_decimal_accepts_brazilian_and_plain_numbers(text: str, expected: Decimal) -> None:
    assert parse_decimal(text) == expected


@pytest.mark.parametrize("text", ["", None, "abc", "1.2.3", "1,2,3", "12a", "NaN", "Infinity"])
def test_parse_decimal_rejects_non_numbers(text: str | None) -> None:
    assert parse_decimal(text) is None


def test_format_decimal_has_no_scientific_notation() -> None:
    assert format_decimal(Decimal("1000")) == "1000"
    assert format_decimal(Decimal("1244.50")) == "1244.5"
    assert format_decimal(Decimal("-0.00")) == "0"


def test_aggregate_separates_empty_and_unknown_and_counts_invalid() -> None:
    rows: list[list[str | None]] = [
        ["A", "1,5"],
        ["A", "x"],
        ["A", ""],
        [None, "2"],
        ["", "3"],
    ]
    result = ag.aggregate(
        rows,
        group_by=[0],
        measures=[(1, "sum"), (1, "count")],
        group_labels=["grupo"],
        measure_labels=["soma", "contagem"],
    )
    by_group = {row[0]: row for row in result.rows}
    assert by_group["A"][1] == "3"  # linhas
    assert by_group["A"][2] == "1.5"  # soma ignora o texto inválido
    assert by_group["A"][3] == "1"  # um inválido
    assert by_group["A"][4] == "2"  # count: não vazios e não desconhecidos
    assert by_group[ag.LABEL_UNKNOWN][1] == "1"
    assert by_group[ag.LABEL_EMPTY][1] == "1"


def test_avg_uses_decimal_and_rounds_half_up() -> None:
    rows: list[list[str | None]] = [["A", "1"], ["A", "2"], ["A", "2"]]
    result = ag.aggregate(
        rows,
        group_by=[0],
        measures=[(1, "avg")],
        group_labels=["g"],
        measure_labels=["média"],
    )
    # 5 / 3 = 1.66666... -> 1.6667 (meio para cima, 4 casas)
    assert result.rows[0][2] == "1.6667"


def test_min_max_and_count_distinct_normalize_text() -> None:
    rows: list[list[str | None]] = [
        ["A", "10"],
        ["A", "9,5"],
        ["A", "10,0"],
        ["A", " AB "],
        ["A", "ab"],
    ]
    result = ag.aggregate(
        rows,
        group_by=[0],
        measures=[(1, "min"), (1, "max"), (1, "count_distinct")],
        group_labels=["g"],
        measure_labels=["mín", "máx", "distintos"],
    )
    row = result.rows[0]
    assert row[2] == "9.5"  # mínimo numérico
    assert row[4] == "10"  # máximo numérico
    # Distintos por texto canônico: "10", "9,5", "10,0", "AB" (sem espaços), "ab" (sem casefold).
    assert row[6] == "5"


def test_aggregate_refuses_too_many_groups() -> None:
    rows: list[list[str | None]] = [[str(i), "1"] for i in range(5)]
    with pytest.raises(ValueError, match="grupos"):
        ag.aggregate(
            rows,
            group_by=[0],
            measures=[(1, "count")],
            group_labels=["g"],
            measure_labels=["n"],
            max_groups=3,
        )


def _import(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (name, data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def test_aggregate_preview_and_derive_keep_source_and_trace(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    source = _import(logged_client, "SYN-agrupado.csv", AGRUPADO)
    body = {
        "dataset_id": source["id"],
        "group_by": ["SYN-Grupo"],
        "measures": [{"column": "SYN-Valor", "op": "sum"}],
    }
    preview = logged_client.post("/api/v1/crossing/aggregate/preview", json=body)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["columns"] == [
        "SYN-Grupo",
        "linhas",
        "soma de SYN-Valor",
        "soma de SYN-Valor (inválidos)",
    ]
    by_group = {row[0]: row for row in data["rows"]}
    assert by_group["A"] == ["A", "3", "1244.5", "1"]
    assert by_group["B"] == ["B", "2", "2.5", "0"]
    assert by_group["C"] == ["C", "1", "-3.25", "0"]

    derived = logged_client.post("/api/v1/crossing/aggregate/derive", json=body)
    assert derived.status_code == 201, derived.text
    out = derived.json()
    assert out["row_count"] == 3
    assert out["counts"]["linhas_lidas"] == 6
    detail = logged_client.get(f"/api/v1/datasets/{out['dataset_id']}").json()
    assert detail["source_kind"] == "derived"
    assert detail["name"].endswith("(Agregação)")
    assert " × " not in detail["name"]  # origem única
    assert logged_client.get(f"/api/v1/datasets/{source['id']}").json()["row_count"] == 6


def test_aggregate_rejects_unknown_column(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    source = _import(logged_client, "SYN-agrupado2.csv", AGRUPADO)
    resp = logged_client.post(
        "/api/v1/crossing/aggregate/preview",
        json={
            "dataset_id": source["id"],
            "group_by": ["NAO-EXISTE"],
            "measures": [{"column": "SYN-Valor", "op": "count"}],
        },
    )
    assert resp.status_code in (400, 422), resp.text
