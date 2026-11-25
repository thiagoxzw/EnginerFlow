"""2B.3: rastreabilidade das tabelas derivadas. Dados sintéticos."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

ESQ = "SYN-Código;SYN-Qtd\n00123;1\n0123;2\nAB1;3\n".encode()
DIR = "SYN-Código;SYN-Descrição\n00123;SYN parafuso\nAB1;SYN arruela\n".encode()


def _import(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (name, data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _derive_lookup(client: TestClient, left: str, right: str) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/crossing/lookup/derive",
        json={
            "left_id": left,
            "right_id": right,
            "left_keys": ["SYN-Código"],
            "right_keys": ["SYN-Código"],
            "return_columns": ["SYN-Descrição"],
        },
    )
    assert resp.status_code == 201, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _rows(client: TestClient, dataset_id: str) -> list[list[str | None]]:
    body = client.get(f"/api/v1/datasets/{dataset_id}/rows?limit=100").json()["rows"]
    return [r["values"] for r in body]


def test_lineage_identifies_operation_sources_versions_and_policy(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-lin-esq.csv", ESQ)
    right = _import(logged_client, "SYN-lin-dir.csv", DIR)
    derived = _derive_lookup(logged_client, left["id"], right["id"])

    lin = logged_client.get(f"/api/v1/datasets/{derived['dataset_id']}/lineage")
    assert lin.status_code == 200, lin.text
    data = lin.json()
    assert data["operation"] == "Super-PROCV"
    assert data["run_id"] == derived["run_id"]
    assert data["params"]["left_id"] == left["id"]
    assert data["params"]["right_id"] == right["id"]
    assert data["params"]["left_keys"] == ["SYN-Código"]
    assert data["policy"]["duplicates"] == "first"
    assert data["counts"]["encontrado"] == 2
    assert data["result_sha256"] == derived["result_sha256"]
    assert len(data["params_sha256"]) == 64
    assert data["created_at"]
    roles = {s["role"]: s for s in data["sources"]}
    assert roles["left"]["dataset_id"] == left["id"]
    assert roles["right"]["dataset_id"] == right["id"]
    assert roles["left"]["version_id"] and roles["left"]["metadata_version_id"]
    assert all(s["still_active"] for s in data["sources"])


def test_lineage_of_plain_import_is_rejected(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    source = _import(logged_client, "SYN-lin-simples.csv", ESQ)
    resp = logged_client.get(f"/api/v1/datasets/{source['id']}/lineage")
    assert resp.status_code in (400, 422), resp.text


def test_derived_table_can_be_origin_of_another_operation(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-lin-esq2.csv", ESQ)
    right = _import(logged_client, "SYN-lin-dir2.csv", DIR)
    derived = _derive_lookup(logged_client, left["id"], right["id"])

    agg = logged_client.post(
        "/api/v1/crossing/aggregate/derive",
        json={
            "dataset_id": derived["dataset_id"],
            "group_by": [],
            "measures": [{"column": "SYN-Qtd", "op": "sum"}],
        },
    )
    assert agg.status_code == 201, agg.text
    lin = logged_client.get(f"/api/v1/datasets/{agg.json()['dataset_id']}/lineage").json()
    assert lin["operation"] == "Agregação"
    assert [s["dataset_id"] for s in lin["sources"]] == [derived["dataset_id"]]
    assert lin["sources"][0]["still_active"] is True


def test_source_deleted_logically_keeps_derived_rows_and_marks_origin(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-lin-esq3.csv", ESQ)
    right = _import(logged_client, "SYN-lin-dir3.csv", DIR)
    derived = _derive_lookup(logged_client, left["id"], right["id"])
    rows_before = _rows(logged_client, derived["dataset_id"])

    deleted = logged_client.request(
        "DELETE", f"/api/v1/datasets/{right['id']}", json={"confirm_name": right["name"]}
    )
    assert deleted.status_code in (200, 204), deleted.text

    assert _rows(logged_client, derived["dataset_id"]) == rows_before  # resultado preservado
    lin = logged_client.get(f"/api/v1/datasets/{derived['dataset_id']}/lineage").json()
    flags = {s["role"]: s["still_active"] for s in lin["sources"]}
    assert flags == {"left": True, "right": False}
