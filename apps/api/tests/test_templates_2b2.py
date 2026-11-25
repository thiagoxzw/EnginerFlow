"""2B.2 bloco 2: modelos de mapeamento reutilizáveis."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

SYN_CSV = (
    "SYN-Código;SYN-Descrição;Qtd\n00123;SYN parafuso;1\n0123;SYN porca;\nAB1;SYN arruela;7\n"
).encode()

MODELO = {"code": "SYN-Código", "description": "SYN-Descrição", "quantity": "Qtd"}


def _import(client: TestClient, data: bytes = SYN_CSV) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-t.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _state(client: TestClient, dataset_id: str) -> tuple[str, str]:
    versions = client.get(f"/api/v1/datasets/{dataset_id}/versions").json()
    metas = client.get(f"/api/v1/datasets/{dataset_id}/metadata-versions").json()
    data_id = next(v["id"] for v in versions if v["is_current"])
    meta_id = next(m["id"] for m in metas if m["is_current"])
    return data_id, meta_id


def _create_template(client: TestClient, name: str, mapping: dict[str, str]) -> dict[str, Any]:
    resp = client.post("/api/v1/templates", json={"name": name, "mapping": mapping})
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _preview_template(
    client: TestClient,
    dataset_id: str,
    template_id: str,
    data_id: str,
    meta_id: str,
    allow_missing: bool = False,
) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/datasets/{dataset_id}/templates/{template_id}/preview",
        json={
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
            "allow_missing": allow_missing,
        },
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _apply(client: TestClient, dataset_id: str, preview_id: str, data_id: str, meta_id: str) -> Any:
    return client.post(
        f"/api/v1/datasets/{dataset_id}/operations",
        json={
            "preview_id": preview_id,
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )


def test_template_names_are_unique_and_listed(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    _create_template(logged_client, "Modelo SYN", MODELO)
    dup = logged_client.post("/api/v1/templates", json={"name": "modelo syn", "mapping": {}})
    assert dup.status_code == 422
    names = [t["name"] for t in logged_client.get("/api/v1/templates").json()]
    assert names == ["Modelo SYN"]


def test_unknown_canonical_field_is_rejected(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    resp = logged_client.post(
        "/api/v1/templates", json={"name": "Errado", "mapping": {"peso": "Qtd"}}
    )
    assert resp.status_code == 422


def test_changing_mapping_bumps_definition_version_but_renaming_does_not(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    tpl = _create_template(logged_client, "Modelo V", MODELO)
    assert tpl["definition_version"] == 1
    renamed = logged_client.patch(f"/api/v1/templates/{tpl['id']}", json={"name": "Modelo W"})
    assert renamed.json()["definition_version"] == 1
    changed = logged_client.patch(
        f"/api/v1/templates/{tpl['id']}", json={"mapping": {"code": "SYN-Código"}}
    )
    assert changed.json()["definition_version"] == 2
    assert changed.json()["mapping"] == {"code": "SYN-Código"}


def test_apply_template_writes_metadata_with_template_reference(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    tpl = _create_template(logged_client, "Modelo A", MODELO)
    data_id, meta_id = _state(logged_client, ds["id"])
    prev = _preview_template(logged_client, ds["id"], tpl["id"], data_id, meta_id)
    assert prev["missing_fields"] == {}
    applied = _apply(logged_client, ds["id"], prev["preview_id"], data_id, meta_id)
    assert applied.status_code == 201, applied.text

    new_data, new_meta = _state(logged_client, ds["id"])
    assert new_data == data_id  # modelo não copia linhas
    metas = logged_client.get(f"/api/v1/datasets/{ds['id']}/metadata-versions").json()
    last = next(m for m in metas if m["id"] == new_meta)
    assert last["mapping"] == MODELO
    assert last["template_id"] == tpl["id"]
    assert len(metas) == 2  # histórico preservado


def test_missing_template_columns_need_explicit_confirmation(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    tpl = _create_template(
        logged_client, "Modelo B", {"code": "SYN-Código", "unit": "Unidade-Inexistente"}
    )
    data_id, meta_id = _state(logged_client, ds["id"])
    prev = _preview_template(logged_client, ds["id"], tpl["id"], data_id, meta_id)
    assert prev["missing_fields"] == {"unit": "Unidade-Inexistente"}
    assert prev["preview_id"] is None  # sem confirmação não há prévia aplicável

    confirmed = _preview_template(
        logged_client, ds["id"], tpl["id"], data_id, meta_id, allow_missing=True
    )
    applied = _apply(logged_client, ds["id"], confirmed["preview_id"], data_id, meta_id)
    assert applied.status_code == 201, applied.text
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["mapping"] == {"code": "SYN-Código"}


def test_editing_template_later_keeps_applied_history_reproducible(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    tpl = _create_template(logged_client, "Modelo C", MODELO)
    data_id, meta_id = _state(logged_client, ds["id"])
    prev = _preview_template(logged_client, ds["id"], tpl["id"], data_id, meta_id)
    _apply(logged_client, ds["id"], prev["preview_id"], data_id, meta_id)

    logged_client.patch(f"/api/v1/templates/{tpl['id']}", json={"mapping": {"code": "SYN-Código"}})

    metas = logged_client.get(f"/api/v1/datasets/{ds['id']}/metadata-versions").json()
    applied_meta = metas[-1]
    assert applied_meta["mapping"] == MODELO
    assert applied_meta["template_id"] == tpl["id"]
    assert applied_meta["template_definition_version"] == 1  # versão usada na aplicação


def test_stale_preview_after_metadata_change_is_rejected_for_templates(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    tpl = _create_template(logged_client, "Modelo D", MODELO)
    data_id, meta_id = _state(logged_client, ds["id"])
    prev = _preview_template(logged_client, ds["id"], tpl["id"], data_id, meta_id)
    logged_client.put(
        f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": "SYN-Código"}}
    )
    stale = _apply(logged_client, ds["id"], prev["preview_id"], data_id, meta_id)
    assert stale.status_code == 409
