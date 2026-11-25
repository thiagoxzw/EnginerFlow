"""2B.3: coluna calculada como tabela derivada rastreável. Dados sintéticos."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

CSV = "SYN-Código;Qtd;Preço\nSYN-001;4;2,5\nSYN-002;;3\nSYN-003;2;\n".encode()


def _import(client: TestClient) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-form.csv", CSV, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _body(ds_id: str, formula: str, new_column: str = "Total") -> dict[str, Any]:
    return {"dataset_id": ds_id, "formula": formula, "new_column": new_column}


def test_preview_computes_values_and_counts_explicit_errors(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    resp = logged_client.post(
        "/api/v1/crossing/formula/preview", json=_body(ds["id"], "[Qtd]*[Preço]")
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["columns"] == ["SYN-Código", "Qtd", "Preço", "Total"]
    by_code = {row[0]: row[3] for row in data["rows"]}
    assert by_code["SYN-001"] == "10"  # 4 * 2,5 com precisão decimal
    assert by_code["SYN-002"] == "#VAZIO!"  # vazio não vira zero
    assert by_code["SYN-003"] == "#VAZIO!"
    assert data["counts"]["erros"] == 2


def test_derive_is_traceable_idempotent_and_keeps_source(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    headers = {"Idempotency-Key": "chave-formula-1"}
    first = logged_client.post(
        "/api/v1/crossing/formula/derive", json=_body(ds["id"], "[Qtd]*2"), headers=headers
    )
    assert first.status_code == 201, first.text
    before = len(logged_client.get("/api/v1/datasets").json())
    second = logged_client.post(
        "/api/v1/crossing/formula/derive", json=_body(ds["id"], "[Qtd]*2"), headers=headers
    )
    assert second.json()["dataset_id"] == first.json()["dataset_id"]
    assert len(logged_client.get("/api/v1/datasets").json()) == before

    detail = logged_client.get(f"/api/v1/datasets/{first.json()['dataset_id']}").json()
    assert detail["source_kind"] == "derived"
    assert detail["columns"][-1] == "Total"
    lin = logged_client.get(f"/api/v1/datasets/{first.json()['dataset_id']}/lineage").json()
    assert lin["operation"] == "Fórmula"
    assert lin["params"]["formula"] == "[Qtd]*2"
    assert [s["dataset_id"] for s in lin["sources"]] == [ds["id"]]
    assert logged_client.get(f"/api/v1/datasets/{ds['id']}").json()["columns"] == [
        "SYN-Código",
        "Qtd",
        "Preço",
    ]


def test_invalid_formula_or_column_is_refused(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    bad = logged_client.post(
        "/api/v1/crossing/formula/preview", json=_body(ds["id"], "__import__('os')")
    )
    assert bad.status_code == 422, bad.text
    missing = logged_client.post(
        "/api/v1/crossing/formula/preview", json=_body(ds["id"], "[Nao existe]+1")
    )
    assert missing.status_code == 422, missing.text
    duplicated = logged_client.post(
        "/api/v1/crossing/formula/preview", json=_body(ds["id"], "[Qtd]+1", new_column="qtd")
    )
    assert duplicated.status_code == 422, duplicated.text
