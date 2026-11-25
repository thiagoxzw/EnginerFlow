"""2B.2 bloco 6: seleção, atualização em lote e exclusão lógica de linhas. Dados sintéticos."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from engiflow_api.application import table_query
from engiflow_api.core.config import Settings

SYN_CSV = (
    "SYN-Código;SYN-Descrição;Qtd\n"
    "SYN-001;Parafuso;10\n"
    "SYN-002;Porca;0\n"
    "SYN-003;Arruela;7,5\n"
    "SYN-004;Pino;\n"
    "SYN-005;Rebite\n"
).encode()


def _import(client: TestClient) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-x.csv", SYN_CSV, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _state(client: TestClient, ds_id: str) -> tuple[str, str]:
    versions = client.get(f"/api/v1/datasets/{ds_id}/versions").json()
    metas = client.get(f"/api/v1/datasets/{ds_id}/metadata-versions").json()
    return (
        next(v["id"] for v in versions if v["is_current"]),
        next(m["id"] for m in metas if m["is_current"]),
    )


def _run(client: TestClient, ds_id: str, code: str, params: dict[str, Any]) -> Any:
    data_id, meta_id = _state(client, ds_id)
    prev = client.post(
        f"/api/v1/datasets/{ds_id}/operations/preview",
        json={
            "code": code,
            "params": params,
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )
    if prev.status_code != 200:
        return prev
    data_id, meta_id = _state(client, ds_id)
    return client.post(
        f"/api/v1/datasets/{ds_id}/operations",
        json={
            "preview_id": prev.json()["preview_id"],
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )


def _rows(client: TestClient, ds_id: str) -> list[dict[str, Any]]:
    body: dict[str, Any] = client.get(f"/api/v1/datasets/{ds_id}/rows?limit=100").json()
    rows: list[dict[str, Any]] = body["rows"]
    return rows


def test_delete_rows_is_logical_keeps_numbers_and_undo_restores(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    applied = _run(logged_client, ds["id"], "delete_rows", {"row_numbers": [3, 5]})
    assert applied.status_code == 201, applied.text
    remaining = [r["row_number"] for r in _rows(logged_client, ds["id"])]
    assert remaining == [2, 4, 6]  # números originais preservados, sem renumeração

    new_data, new_meta = _state(logged_client, ds["id"])
    undone = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/undo",
        json={"base_version_id": new_data, "base_metadata_version_id": new_meta},
    )
    assert undone.status_code == 200, undone.text
    assert [r["row_number"] for r in _rows(logged_client, ds["id"])] == [2, 3, 4, 5, 6]


def test_delete_unknown_row_is_rejected_at_preview(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    resp = _run(logged_client, ds["id"], "delete_rows", {"row_numbers": [99]})
    assert resp.status_code == 422
    assert len(_rows(logged_client, ds["id"])) == 5


def test_batch_set_value_accepts_text_empty_and_unknown(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    applied = _run(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2, 3], "column": "Qtd", "value": None},
    )
    assert applied.status_code == 201, applied.text
    # Cabeçalho ocupa a linha 1: dados começam na linha 2 (SYN-001 na 2, SYN-002 na 3...).
    rows = {r["row_number"]: r["values"] for r in _rows(logged_client, ds["id"])}
    assert rows[2][2] is None  # desconhecido definido explicitamente
    assert rows[3][2] is None
    assert rows[4][2] == "7,5"  # linha não selecionada intocada
    assert rows[3][0] == "SYN-002"  # código preservado

    second = _run(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [5], "column": "Qtd", "value": ""},
    )
    assert second.status_code == 201, second.text
    assert {r["row_number"]: r["values"] for r in _rows(logged_client, ds["id"])}[5][2] == ""


def test_selection_by_filter_returns_matching_numbers(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    resp = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/rows/selection",
        json={"filters": [{"column": "Qtd", "op": "gte", "value": "7"}]},
    )
    assert resp.status_code == 200, resp.text
    # Linha 2 (10) e linha 4 (7,5); a linha 3 tem 0 e não casa.
    assert resp.json() == {"count": 2, "row_numbers": [2, 4]}


def test_selection_by_search_ignores_accents(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    resp = logged_client.post(f"/api/v1/datasets/{ds['id']}/rows/selection", json={"q": "pino"})
    assert resp.json()["row_numbers"] == [5]  # "Pino" está na linha 5


def test_selection_above_cap_is_refused_with_guidance(
    logged_client: TestClient, storage_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(table_query, "MAX_SELECTED_ROWS", 2)
    ds = _import(logged_client)
    resp = logged_client.post(f"/api/v1/datasets/{ds['id']}/rows/selection", json={})
    assert resp.status_code == 422
    assert "Refine os filtros" in resp.text
