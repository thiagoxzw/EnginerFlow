"""2B.2 bloco 3: seleção manual de cabeçalho (reconstrução a partir do arquivo original)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

# Linha 1 e 2 são título; cabeçalho real na linha 3. Zeros à esquerda devem sobreviver.
SYN_CSV = (
    "SYN relatório de peças\n\nSYN-Código;SYN-Descrição;Qtd\n"
    "00123;SYN parafuso;1\n0123;SYN porca;\nAB1;SYN arruela;7\n"
).encode()


def _import(client: TestClient) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-h.csv", SYN_CSV, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _state(client: TestClient, dataset_id: str) -> tuple[str, str]:
    versions = client.get(f"/api/v1/datasets/{dataset_id}/versions").json()
    metas = client.get(f"/api/v1/datasets/{dataset_id}/metadata-versions").json()
    return (
        next(v["id"] for v in versions if v["is_current"]),
        next(m["id"] for m in metas if m["is_current"]),
    )


def _preview_header(client: TestClient, dataset_id: str, header_row: int) -> Any:
    data_id, meta_id = _state(client, dataset_id)
    return client.post(
        f"/api/v1/datasets/{dataset_id}/operations/preview",
        json={
            "code": "set_header_row",
            "params": {"header_row": header_row},
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )


def _apply(client: TestClient, dataset_id: str, preview_id: str, data_id: str, meta_id: str) -> Any:
    return client.post(
        f"/api/v1/datasets/{dataset_id}/operations",
        json={
            "preview_id": preview_id,
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )


def test_raw_head_exposes_numbered_source_rows(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    body = logged_client.get(f"/api/v1/datasets/{ds['id']}/raw-head?count=4").json()
    assert [r["row_number"] for r in body] == [1, 2, 3, 4]
    assert body[2]["values"][0] == "SYN-Código"


def test_choosing_header_rebuilds_from_original_and_keeps_codes(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview_header(logged_client, ds["id"], 3)
    assert prev.status_code == 200, prev.text
    data_id, meta_id = _state(logged_client, ds["id"])
    applied = _apply(logged_client, ds["id"], prev.json()["preview_id"], data_id, meta_id)
    assert applied.status_code == 201, applied.text

    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["columns"] == ["SYN-Código", "SYN-Descrição", "Qtd"]
    assert detail["row_count"] == 3
    rows = logged_client.get(f"/api/v1/datasets/{ds['id']}/rows?limit=10").json()["rows"]
    assert [r["values"][0] for r in rows] == ["00123", "0123", "AB1"]  # zeros preservados
    assert rows[1]["values"][2] is None or rows[1]["values"][2] == ""  # vazio continua vazio

    metas = logged_client.get(f"/api/v1/datasets/{ds['id']}/metadata-versions").json()
    assert metas[-1]["header_row"] == 3


def test_header_change_keeps_history_and_undo_restores_previous_table(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    before = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()["columns"]
    prev = _preview_header(logged_client, ds["id"], 3)
    data_id, meta_id = _state(logged_client, ds["id"])
    _apply(logged_client, ds["id"], prev.json()["preview_id"], data_id, meta_id)
    assert len(logged_client.get(f"/api/v1/datasets/{ds['id']}/versions").json()) == 2

    new_data, new_meta = _state(logged_client, ds["id"])
    undone = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/undo",
        json={"base_version_id": new_data, "base_metadata_version_id": new_meta},
    )
    assert undone.status_code == 200, undone.text
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["columns"] == before  # histórico preservado, undo restaura a versão anterior
    assert len(logged_client.get(f"/api/v1/datasets/{ds['id']}/versions").json()) == 2


def test_header_row_beyond_source_is_rejected_without_changes(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    prev = _preview_header(logged_client, ds["id"], 99)
    assert prev.status_code == 422
    assert len(logged_client.get(f"/api/v1/datasets/{ds['id']}/versions").json()) == 1


def test_stale_header_preview_is_rejected_after_mapping_change(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    before = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()["columns"]
    prev = _preview_header(logged_client, ds["id"], 3)
    logged_client.put(f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": before[0]}})
    data_id, meta_id = _state(logged_client, ds["id"])
    stale = _apply(logged_client, ds["id"], prev.json()["preview_id"], data_id, meta_id)
    assert stale.status_code == 409
    assert logged_client.get(f"/api/v1/datasets/{ds['id']}").json()["columns"] == before
