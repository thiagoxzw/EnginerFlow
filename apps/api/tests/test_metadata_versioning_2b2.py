"""2B.2 bloco 1: versionamento de mapeamentos e metadados.

Garantias verificadas:
- mapeamento gera versão de METADADOS e não copia linhas (mesma versão de dados);
- desfazer mapeamento restaura o mapeamento anterior sem perder histórico;
- prévia gerada antes de uma mudança de metadados é recusada (409) e nada muda;
- undo/redo exigem os dois ponteiros (dados e metadados) atuais.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

SYN_CSV = (
    "SYN-Código;SYN-Descrição;Qtd\n00123;SYN parafuso;1\n0123;SYN porca;\nAB1;SYN arruela;7\n"
).encode()


def _import(client: TestClient) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-m.csv", SYN_CSV, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _state(client: TestClient, dataset_id: str) -> tuple[str, str]:
    """(versão de dados atual, versão de metadados atual) conforme a API."""
    versions = client.get(f"/api/v1/datasets/{dataset_id}/versions").json()
    metas = client.get(f"/api/v1/datasets/{dataset_id}/metadata-versions").json()
    data_id = next(v["id"] for v in versions if v["is_current"])
    meta_id = next(m["id"] for m in metas if m["is_current"])
    return data_id, meta_id


def _preview(
    client: TestClient,
    dataset_id: str,
    code: str,
    params: dict[str, Any],
    data_id: str,
    meta_id: str,
) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/datasets/{dataset_id}/operations/preview",
        json={
            "code": code,
            "params": params,
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def test_mapping_creates_metadata_version_without_copying_rows(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    data_before, meta_before = _state(logged_client, ds["id"])

    resp = logged_client.put(
        f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": "SYN-Código"}}
    )
    assert resp.status_code == 200, resp.text

    data_after, meta_after = _state(logged_client, ds["id"])
    assert data_after == data_before  # sem nova versão de dados
    assert meta_after != meta_before  # nova versão de metadados
    versions = logged_client.get(f"/api/v1/datasets/{ds['id']}/versions").json()
    assert len(versions) == 1
    metas = logged_client.get(f"/api/v1/datasets/{ds['id']}/metadata-versions").json()
    assert [m["number"] for m in metas] == [1, 2]
    assert metas[-1]["mapping"] == {"code": "SYN-Código"}
    assert metas[0]["mapping"] == {}  # histórico preservado
    assert metas[-1]["metadata_sha256"] != metas[0]["metadata_sha256"]


def test_undo_mapping_restores_previous_mapping_and_keeps_history(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    logged_client.put(
        f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": "SYN-Código"}}
    )
    data_id, meta_id = _state(logged_client, ds["id"])

    undone = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/undo",
        json={"base_version_id": data_id, "base_metadata_version_id": meta_id},
    )
    assert undone.status_code == 200, undone.text
    body = undone.json()
    assert body["current_version_id"] == data_id
    metas = logged_client.get(f"/api/v1/datasets/{ds['id']}/metadata-versions").json()
    assert body["current_metadata_version_id"] == metas[0]["id"]
    assert len(metas) == 2  # nada apagado
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["mapping"] == {}


def test_preview_is_rejected_after_metadata_changed(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    data_id, meta_v1 = _state(logged_client, ds["id"])
    prev = _preview(
        logged_client,
        ds["id"],
        "rename_column",
        {"from_name": "Qtd", "to_name": "Quantidade"},
        data_id,
        meta_v1,
    )
    # Outra mudança de metadados (mapeamento) invalida a prévia anterior.
    logged_client.put(
        f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": "SYN-Código"}}
    )
    stale = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/operations",
        json={
            "preview_id": prev["preview_id"],
            "base_version_id": data_id,
            "base_metadata_version_id": meta_v1,
        },
    )
    assert stale.status_code == 409, stale.text
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["columns"] == ["SYN-Código", "SYN-Descrição", "Qtd"]  # nada mudou


def test_legacy_requests_without_metadata_base_cannot_overwrite_stale_metadata(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    """Cliente 2B.1 (sem base de metadados): a prévia guarda os metadados vistos no momento
    da prévia. Se os metadados mudarem antes da aplicação, a aplicação é recusada."""
    ds = _import(logged_client)
    data_id, _ = _state(logged_client, ds["id"])
    prev = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/operations/preview",
        json={
            "code": "rename_column",
            "params": {"from_name": "Qtd", "to_name": "Quantidade"},
            "base_version_id": data_id,
        },
    )
    assert prev.status_code == 200, prev.text
    logged_client.put(
        f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": "SYN-Código"}}
    )
    stale = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/operations",
        json={"preview_id": prev.json()["preview_id"], "base_version_id": data_id},
    )
    assert stale.status_code == 409, stale.text
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["columns"][2] == "Qtd"


def test_rename_is_metadata_only_and_undo_restores_name(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    data_id, meta_id = _state(logged_client, ds["id"])
    prev = _preview(
        logged_client,
        ds["id"],
        "rename_column",
        {"from_name": "Qtd", "to_name": "Quantidade"},
        data_id,
        meta_id,
    )
    applied = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/operations",
        json={
            "preview_id": prev["preview_id"],
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["current_version_id"] == data_id  # só metadados
    new_data_id, new_meta_id = _state(logged_client, ds["id"])
    assert new_data_id == data_id
    assert new_meta_id != meta_id

    undone = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/undo",
        json={"base_version_id": new_data_id, "base_metadata_version_id": new_meta_id},
    )
    assert undone.status_code == 200, undone.text
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["columns"][2] == "Qtd"
