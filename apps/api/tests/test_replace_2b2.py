"""2B.2 bloco 5: localizar e substituir em lote, com colunas e filtros. Dados sintéticos."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

SYN_CSV = (
    "SYN-Código;SYN-Descrição;Qtd\n"
    "SYN-001;Parafuso-M8 zincado;10\n"
    "SYN-002;Porca-M8;0\n"
    "SYN-003;Arruela-M8 lisa;\n"
    "SYN-004;Pino-M10;7,5\n"
    "SYN-005;Item sem quantidade;\n"
    "SYN-006;Sem qtd\n"
).encode()


def _import(client: TestClient) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-r.csv", SYN_CSV, "text/csv")})
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


def _preview(client: TestClient, ds_id: str, params: dict[str, Any]) -> Any:
    data_id, meta_id = _state(client, ds_id)
    return client.post(
        f"/api/v1/datasets/{ds_id}/operations/preview",
        json={
            "code": "replace_text",
            "params": params,
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )


def _apply(client: TestClient, ds_id: str, preview_id: str) -> Any:
    data_id, meta_id = _state(client, ds_id)
    return client.post(
        f"/api/v1/datasets/{ds_id}/operations",
        json={
            "preview_id": preview_id,
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )


def _values(client: TestClient, ds_id: str) -> list[list[str | None]]:
    rows = client.get(f"/api/v1/datasets/{ds_id}/rows?limit=100").json()["rows"]
    return [r["values"] for r in rows]


def test_replace_in_one_column_reports_rows_and_cells(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview(
        logged_client,
        ds["id"],
        {"column": "SYN-Descrição", "find": "M8", "replace": "M-8"},
    )
    assert prev.status_code == 200, prev.text
    assert prev.json()["rows_affected"] == 3
    assert prev.json()["cells_changed"] == 3
    assert _apply(logged_client, ds["id"], prev.json()["preview_id"]).status_code == 201
    values = _values(logged_client, ds["id"])
    assert values[0][1] == "Parafuso-M-8 zincado"
    assert values[3][1] == "Pino-M10"  # linha sem a palavra não muda


def test_multiple_columns_are_counted_per_row_and_per_cell(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview(
        logged_client,
        ds["id"],
        {"columns": ["SYN-Código", "SYN-Descrição"], "find": "SYN", "replace": "ABC"},
    )
    assert prev.json()["rows_affected"] == 6  # uma célula por linha em SYN-Código
    assert prev.json()["cells_changed"] == 6


def test_filter_limits_which_rows_change(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview(
        logged_client,
        ds["id"],
        {
            "column": "SYN-Descrição",
            "find": "-",
            "replace": "_",
            "filters": [{"column": "Qtd", "op": "gt", "value": "5"}],
        },
    )
    assert prev.json()["rows_affected"] == 2  # só 10 e 7,5
    _apply(logged_client, ds["id"], prev.json()["preview_id"])
    values = _values(logged_client, ds["id"])
    assert values[0][1] == "Parafuso_M8 zincado"
    assert values[1][1] == "Porca-M8"  # Qtd 0 não casa com "maior que 5"
    assert values[3][1] == "Pino_M10"


def test_whole_cell_replace_only_touches_exact_match(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview(
        logged_client,
        ds["id"],
        {"column": "Qtd", "find": "0", "replace": "zero", "whole_cell": True},
    )
    assert prev.json()["rows_affected"] == 1  # só a célula "0"; "10" não muda
    _apply(logged_client, ds["id"], prev.json()["preview_id"])
    values = _values(logged_client, ds["id"])
    assert values[0][2] == "10"
    assert values[1][2] == "zero"


def test_unknown_values_are_never_replaced(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview(logged_client, ds["id"], {"column": "Qtd", "find": "7", "replace": "9"})
    _apply(logged_client, ds["id"], prev.json()["preview_id"])
    last = _values(logged_client, ds["id"])[-1]
    assert last[2] is None  # desconhecido permanece desconhecido


def test_stale_preview_is_rejected_after_table_changed(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview(logged_client, ds["id"], {"column": "Qtd", "find": "1", "replace": "2"})
    logged_client.put(
        f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": "SYN-Código"}}
    )
    stale = _apply(logged_client, ds["id"], prev.json()["preview_id"])
    assert stale.status_code == 409


def test_unknown_column_or_filter_is_a_rule_error(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    bad_column = _preview(
        logged_client, ds["id"], {"columns": ["Nope"], "find": "a", "replace": "b"}
    )
    assert bad_column.status_code == 422
    bad_filter = _preview(
        logged_client,
        ds["id"],
        {
            "column": "Qtd",
            "find": "1",
            "replace": "2",
            "filters": [{"column": "Nope", "op": "eq", "value": "x"}],
        },
    )
    assert bad_filter.status_code == 422
