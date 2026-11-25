"""2B.2 bloco 4: filtros, pesquisa, ordenação e paginação no servidor. Dados sintéticos."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings
from engiflow_api.domain.query import fold, parse_number

# Qtd: "10", vazio, "7,5", "0", "3", ausente (desconhecido, linha curta).
SYN_CSV = (
    "SYN-Código;SYN-Descrição;Qtd\n"
    "00123;Parafuso Sextavado;10\n"
    "0123;Porca Sextavada;\n"
    "AB1;Arruela Lisa;7,5\n"
    "ABC;Ação Especial;0\n"
    ";Sem código;3\n"
    "XYZ;Item sem quantidade\n"
).encode()


def _import(client: TestClient) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-q.csv", SYN_CSV, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _rows(client: TestClient, ds_id: str, **params: Any) -> dict[str, Any]:
    if "filters" in params:
        params["filters"] = json.dumps(params["filters"])
    resp = client.get(f"/api/v1/datasets/{ds_id}/rows", params={"limit": 100, **params})
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _codes(body: dict[str, Any]) -> list[str | None]:
    return [r["values"][0] for r in body["rows"]]


# ---------- regras puras ----------


def test_parse_number_accepts_decimal_comma_and_rejects_text() -> None:
    assert parse_number("7,5") == Decimal("7.5")
    assert parse_number("0") == Decimal("0")
    assert parse_number(" 10 ") == Decimal("10")
    assert parse_number("M8") is None
    assert parse_number("") is None
    assert parse_number(None) is None


def test_fold_ignores_accents_and_case() -> None:
    assert fold("Ação ESPECIAL") == fold("acao especial")


# ---------- filtros ----------


def test_text_equality_preserves_leading_zeros(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    body = _rows(
        logged_client,
        ds["id"],
        filters=[{"column": "SYN-Código", "op": "eq", "value": "00123"}],
    )
    assert _codes(body) == ["00123"]
    assert body["total"] == 1


def test_contains_is_accent_insensitive(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    body = _rows(
        logged_client,
        ds["id"],
        filters=[{"column": "SYN-Descrição", "op": "contains", "value": "acao"}],
    )
    assert _codes(body) == ["ABC"]


def test_numeric_comparison_separates_unknown_empty_and_zero(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    gt = _rows(logged_client, ds["id"], filters=[{"column": "Qtd", "op": "gt", "value": "5"}])
    assert _codes(gt) == ["00123", "AB1"]  # 10 e 7,5; vazio, zero e desconhecido não casam

    between = _rows(
        logged_client,
        ds["id"],
        filters=[{"column": "Qtd", "op": "between", "value": "0", "value2": "7,5"}],
    )
    # Inclui 7,5, zero e 3 (linha com código vazio); exclui vazio e desconhecido.
    assert _codes(between) == ["AB1", "ABC", ""]


def test_state_operators_distinguish_empty_unknown_and_zero(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    empty = _rows(logged_client, ds["id"], filters=[{"column": "Qtd", "op": "is_empty"}])
    assert _codes(empty) == ["0123"]
    unknown = _rows(logged_client, ds["id"], filters=[{"column": "Qtd", "op": "is_unknown"}])
    assert _codes(unknown) == ["XYZ"]
    zero = _rows(logged_client, ds["id"], filters=[{"column": "Qtd", "op": "is_zero"}])
    assert _codes(zero) == ["ABC"]


def test_filters_combine_with_and(logged_client: TestClient, storage_settings: Settings) -> None:
    ds = _import(logged_client)
    body = _rows(
        logged_client,
        ds["id"],
        filters=[
            {"column": "SYN-Descrição", "op": "contains", "value": "sextavad"},
            {"column": "Qtd", "op": "gte", "value": "10"},
        ],
    )
    assert _codes(body) == ["00123"]


# ---------- pesquisa, ordenação e paginação ----------


def test_global_search_ignores_case_and_accents(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    assert _codes(_rows(logged_client, ds["id"], q="PARAFUSO")) == ["00123"]
    assert _codes(_rows(logged_client, ds["id"], q="acao")) == ["ABC"]


def test_numeric_sort_puts_unknown_last_in_both_directions(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    # Numéricos antes de textuais (vazio), desconhecido sempre por último.
    asc = _rows(logged_client, ds["id"], sort="Qtd", dir="asc")
    assert [r["values"][2] for r in asc["rows"]] == ["0", "3", "7,5", "10", "", None]

    desc = _rows(logged_client, ds["id"], sort="Qtd", dir="desc")
    assert [r["values"][2] for r in desc["rows"]] == ["", "10", "7,5", "3", "0", None]


def test_pagination_reports_matching_total_and_pages_consistently(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    first = _rows(logged_client, ds["id"], sort="SYN-Código", dir="asc", limit=2, offset=0)
    second = _rows(logged_client, ds["id"], sort="SYN-Código", dir="asc", limit=2, offset=2)
    assert first["total"] == second["total"] == 6
    seen = [r["row_number"] for r in first["rows"] + second["rows"]]
    assert len(seen) == len(set(seen)) == 4  # sem repetição entre páginas


def test_filters_change_total_not_stored_values(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    body = _rows(logged_client, ds["id"], filters=[{"column": "Qtd", "op": "eq", "value": "7,5"}])
    assert body["total"] == 1
    assert body["rows"][0]["values"][2] == "7,5"  # valor original preservado


@pytest.mark.parametrize(
    "bad",
    [
        {"column": "Inexistente", "op": "eq", "value": "x"},
        {"column": "Qtd", "op": "gt", "value": "abc"},
        {"column": "Qtd", "op": "between", "value": "9", "value2": "1"},
        {"column": "Qtd", "op": "eq"},
        {"column": "Qtd", "op": "regex", "value": "x"},
    ],
)
def test_invalid_filters_are_rejected_with_rule_error(
    logged_client: TestClient, storage_settings: Settings, bad: dict[str, Any]
) -> None:
    ds = _import(logged_client)
    resp = logged_client.get(
        f"/api/v1/datasets/{ds['id']}/rows", params={"filters": json.dumps([bad])}
    )
    assert resp.status_code == 422, resp.text


def test_malformed_filter_json_is_rejected(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    resp = logged_client.get(f"/api/v1/datasets/{ds['id']}/rows", params={"filters": "{nao-json"})
    assert resp.status_code == 422
