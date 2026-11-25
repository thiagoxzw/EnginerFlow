"""2B.3: colagem em UMA operação (set_cells): validação, histórico único, desfazer."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

SYN_CSV = (
    "SYN-Código;SYN-Descrição;Qtd\nSYN-001;Parafuso;007\nSYN-002;Porca;0\nSYN-003;Arruela;\n"
).encode()


def _import(client: TestClient) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-cel.csv", SYN_CSV, "text/csv")})
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


def _preview(client: TestClient, ds_id: str, cells: list[dict[str, Any]]) -> Any:
    data_id, meta_id = _state(client, ds_id)
    return client.post(
        f"/api/v1/datasets/{ds_id}/operations/preview",
        json={
            "code": "set_cells",
            "params": {"cells": cells},
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


def test_paste_is_one_history_entry_and_undo_restores_all_cells(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    before = _values(logged_client, ds["id"])
    cells = [
        {"row_number": 2, "column": "SYN-Descrição", "value": "Porca sextavada"},
        {"row_number": 3, "column": "Qtd", "value": "0010"},
        {"row_number": 4, "column": "SYN-Código", "value": None},  # desconhecido
    ]
    prev = _preview(logged_client, ds["id"], cells)
    assert prev.status_code == 200, prev.text
    applied = _apply(logged_client, ds["id"], prev.json()["preview_id"])
    assert applied.status_code in (200, 201), applied.text

    # Índice 0 = linha 2 (a linha 1 é o cabeçalho): row_number N está no índice N-2.
    after = _values(logged_client, ds["id"])
    assert after[0][1] == "Porca sextavada"  # linha 2, descrição
    assert after[0][2] == "007"  # linha 2, quantidade não colada permanece
    assert after[1][2] == "0010"  # linha 3, zero à esquerda preservado
    assert after[2][0] is None  # linha 4, desconhecido gravado como desconhecido

    ops = logged_client.get(f"/api/v1/datasets/{ds['id']}/operations").json()
    applied_ops = [o for o in ops if o["status"] == "applied"]
    assert len(applied_ops) == 1  # uma única entrada para a colagem inteira
    assert applied_ops[0]["code"] == "set_cells"

    undone = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/undo", json=_undo_body(logged_client, ds["id"])
    )
    assert undone.status_code == 200, undone.text
    assert _values(logged_client, ds["id"]) == before


def test_paste_with_missing_row_is_refused_before_any_change(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    before = _values(logged_client, ds["id"])
    prev = _preview(
        logged_client,
        ds["id"],
        [
            {"row_number": 2, "column": "SYN-Descrição", "value": "X"},
            {"row_number": 99, "column": "SYN-Descrição", "value": "Y"},
        ],
    )
    assert prev.status_code in (400, 422), prev.text
    assert _values(logged_client, ds["id"]) == before


def test_paste_with_unknown_column_is_refused(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview(
        logged_client, ds["id"], [{"row_number": 2, "column": "NAO-EXISTE", "value": "X"}]
    )
    assert prev.status_code in (400, 422), prev.text


def _undo_body(client: TestClient, ds_id: str) -> dict[str, Any]:
    data_id, meta_id = _state(client, ds_id)
    return {"base_version_id": data_id, "base_metadata_version_id": meta_id}
