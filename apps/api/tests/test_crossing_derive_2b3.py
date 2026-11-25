"""2B.3 bloco 1: tabela derivada do Super-PROCV, rastreabilidade e exportação. Dados sintéticos."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

CONSULTA = "SYN-Código;SYN-Qtd\n00123;1\n0123;2\nAB1;3\n".encode()
BUSCA = "SYN-Código;SYN-Descrição\n00123;SYN parafuso\nAB1;SYN arruela\n".encode()


def _import(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (name, data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _body(left: str, right: str) -> dict[str, Any]:
    return {
        "left_id": left,
        "right_id": right,
        "left_keys": ["SYN-Código"],
        "right_keys": ["SYN-Código"],
        "return_columns": ["SYN-Descrição"],
    }


def _state(client: TestClient, ds_id: str) -> tuple[str, str]:
    versions = client.get(f"/api/v1/datasets/{ds_id}/versions").json()
    metas = client.get(f"/api/v1/datasets/{ds_id}/metadata-versions").json()
    return (
        next(v["id"] for v in versions if v["is_current"]),
        next(m["id"] for m in metas if m["is_current"]),
    )


def _values(client: TestClient, ds_id: str) -> list[list[str | None]]:
    rows: list[dict[str, Any]] = client.get(f"/api/v1/datasets/{ds_id}/rows?limit=100").json()[
        "rows"
    ]
    return [r["values"] for r in rows]


def test_derive_creates_traced_table_and_keeps_sources(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    left_before = _state(logged_client, left["id"])
    right_before = _state(logged_client, right["id"])

    resp = logged_client.post("/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"]))
    assert resp.status_code == 201, resp.text
    derived = resp.json()
    assert derived["row_count"] == 3
    assert derived["counts"]["encontrado"] == 2  # 00123 e AB1
    assert derived["counts"]["não encontrado"] == 1  # 0123

    detail = logged_client.get(f"/api/v1/datasets/{derived['dataset_id']}").json()
    assert "SYN-Descrição" in detail["columns"]
    values = _values(logged_client, derived["dataset_id"])
    assert values[0][0] == "00123"  # zeros preservados na derivada
    assert values[1][0] == "0123"

    # Origens inalteradas: mesmas versões atuais.
    assert _state(logged_client, left["id"]) == left_before
    assert _state(logged_client, right["id"]) == right_before


def test_editing_a_source_later_does_not_change_the_derived_table(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    derived = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"])
    ).json()
    before = _values(logged_client, derived["dataset_id"])

    data_id, meta_id = _state(logged_client, left["id"])
    prev = logged_client.post(
        f"/api/v1/datasets/{left['id']}/operations/preview",
        json={
            "code": "replace_text",
            "params": {"column": "SYN-Código", "find": "00123", "replace": "99999"},
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    ).json()
    applied = logged_client.post(
        f"/api/v1/datasets/{left['id']}/operations",
        json={
            "preview_id": prev["preview_id"],
            "base_version_id": data_id,
            "base_metadata_version_id": meta_id,
        },
    )
    assert applied.status_code == 201, applied.text

    assert _values(logged_client, left["id"])[0][0] == "99999"  # origem mudou
    assert _values(logged_client, derived["dataset_id"]) == before  # derivada não mudou


def test_two_derivations_of_same_inputs_have_same_result_hash(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    first = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"])
    ).json()
    second = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"])
    ).json()
    assert first["dataset_id"] != second["dataset_id"]
    assert first["result_sha256"] == second["result_sha256"]
    assert first["run_id"] != second["run_id"]


def test_export_csv_keeps_codes_and_uses_semicolon(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    resp = logged_client.post(
        "/api/v1/crossing/lookup/export?format=csv", json=_body(left["id"], right["id"])
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="super-procv.csv"' in resp.headers["content-disposition"]
    text = resp.content.decode("utf-8-sig")
    assert text.splitlines()[1].startswith("00123;")
    assert text.splitlines()[2].startswith("0123;")  # zero à esquerda preservado no CSV


def test_export_xlsx_is_served_as_spreadsheet(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    resp = logged_client.post(
        "/api/v1/crossing/lookup/export?format=xlsx", json=_body(left["id"], right["id"])
    )
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml" in resp.headers["content-type"]
    assert resp.content[:2] == b"PK"  # arquivo XLSX é um zip
