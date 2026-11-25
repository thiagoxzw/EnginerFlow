"""Fase 3: operações estruturais pelo caminho HTTP (prévia, aplicação, histórico e desfazer).

Dados sintéticos apenas (SYN-*). Mesmo padrão de test_set_cells_2b3.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

SYN_CSV = "SYN-Código;SYN-Descrição;Qtd\nSYN-001;Parafuso;007\nSYN-002;Porca;0\n".encode()


def _import(client: TestClient) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-est.csv", SYN_CSV, "text/csv")})
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


def _run(client: TestClient, ds_id: str, code: str, params: dict[str, Any]) -> None:
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
    assert prev.status_code == 200, prev.text
    data_id, meta_id = _state(client, ds_id)
    applied = client.post(
        f"/api/v1/datasets/{ds_id}/operations",
        json={
            "preview_id": prev.json()["preview_id"],
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )
    assert applied.status_code in (200, 201), applied.text


def _undo(client: TestClient, ds_id: str) -> None:
    data_id, meta_id = _state(client, ds_id)
    resp = client.post(
        f"/api/v1/datasets/{ds_id}/undo",
        json={"base_version_id": data_id, "base_metadata_version_id": meta_id},
    )
    assert resp.status_code == 200, resp.text


def _table(client: TestClient, ds_id: str) -> tuple[list[str], list[list[str | None]]]:
    detail = client.get(f"/api/v1/datasets/{ds_id}").json()
    rows = client.get(f"/api/v1/datasets/{ds_id}/rows?limit=100").json()["rows"]
    return list(detail["columns"]), [r["values"] for r in rows]


def test_insert_rows_then_undo_restores_the_table(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    before = _table(logged_client, ds["id"])
    _run(logged_client, ds["id"], "insert_rows", {"after_row_number": 2, "count": 2})
    columns, rows = _table(logged_client, ds["id"])
    assert len(rows) == len(before[1]) + 2
    assert rows[1] == ["", "", ""]  # linhas novas vazias, depois da linha 2
    _undo(logged_client, ds["id"])
    assert _table(logged_client, ds["id"]) == before


def test_duplicate_column_and_undo(logged_client: TestClient, storage_settings: Settings) -> None:
    ds = _import(logged_client)
    before = _table(logged_client, ds["id"])
    _run(
        logged_client,
        ds["id"],
        "duplicate_column",
        {"column": "Qtd", "name": "Qtd cópia"},
    )
    columns, rows = _table(logged_client, ds["id"])
    assert columns == ["SYN-Código", "SYN-Descrição", "Qtd", "Qtd cópia"]
    assert rows[0][2] == rows[0][3] == "007"  # zero à esquerda preservado na cópia
    _undo(logged_client, ds["id"])
    assert _table(logged_client, ds["id"]) == before


def test_delete_column_is_logical_and_undo_brings_it_back(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    before = _table(logged_client, ds["id"])
    _run(logged_client, ds["id"], "delete_columns", {"columns": ["Qtd"]})
    columns, _ = _table(logged_client, ds["id"])
    assert "Qtd" not in columns
    _undo(logged_client, ds["id"])
    assert _table(logged_client, ds["id"]) == before


def test_duplicate_rows_increases_count_and_undo_restores(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    before = _table(logged_client, ds["id"])
    _run(logged_client, ds["id"], "duplicate_rows", {"row_numbers": [2]})
    _, rows = _table(logged_client, ds["id"])
    assert len(rows) == len(before[1]) + 1
    assert rows[0] == rows[1]
    _undo(logged_client, ds["id"])
    assert _table(logged_client, ds["id"]) == before


def test_structural_change_does_not_alter_derived_table_or_its_lineage(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    """Renumerar linhas da origem não muda a derivada (versão congelada) nem a rastreabilidade."""
    source = _import(logged_client)
    derived = logged_client.post(
        "/api/v1/crossing/formula/derive",
        json={"dataset_id": source["id"], "formula": "[Qtd]", "new_column": "Qtd copiada"},
    )
    assert derived.status_code == 201, derived.text
    derived_id = derived.json()["dataset_id"]
    derived_before = _table(logged_client, derived_id)
    lineage_before = logged_client.get(f"/api/v1/datasets/{derived_id}/lineage").json()

    _run(logged_client, source["id"], "insert_rows", {"after_row_number": 2, "count": 3})
    _run(logged_client, source["id"], "duplicate_rows", {"row_numbers": [3]})

    # A derivada não muda: continua com as linhas congeladas no momento da criação.
    assert _table(logged_client, derived_id) == derived_before
    # A rastreabilidade continua apontando para a mesma origem e versão.
    lineage_after = logged_client.get(f"/api/v1/datasets/{derived_id}/lineage").json()
    assert lineage_after == lineage_before
    # A origem, por outro lado, tem as linhas novas.
    assert len(_table(logged_client, source["id"])[1]) == len(derived_before[1]) + 4
