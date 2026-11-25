"""2B.3 bloco 1: Super-PROCV pela API (prévia). Dados sintéticos; nada é gravado."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from engiflow_api.application import crossing
from engiflow_api.core.config import Settings

CONSULTA = ("SYN-Código;SYN-Qtd\n00123;1\n0123;2\nAB1;3\nXYZ;4\n;5\n").encode()
BUSCA = (
    "SYN-Código;SYN-Descrição\n00123;SYN parafuso\nAB1;SYN arruela\nAB1;SYN arruela alternativa\n"
).encode()


def _import(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (name, data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _preview(client: TestClient, left: str, right: str, **extra: Any) -> Any:
    body = {
        "left_id": left,
        "right_id": right,
        "left_keys": ["SYN-Código"],
        "right_keys": ["SYN-Código"],
        "return_columns": ["SYN-Descrição"],
        **extra,
    }
    return client.post("/api/v1/crossing/lookup/preview", json=body)


def test_preview_counts_statuses_and_preserves_codes(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    resp = _preview(logged_client, left["id"], right["id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    counts = body["counts"]
    assert counts["encontrado"] == 1  # 00123 casa com 00123 (não com 0123)
    assert counts["não encontrado"] == 2  # 0123 e XYZ
    assert counts["múltiplas correspondências"] == 1  # AB1 aparece duas vezes na busca
    assert counts["chave inválida"] == 1  # código vazio nunca casa
    assert body["columns"][-2:] == ["_status", "_correspondencias"]
    assert "SYN-Descrição" in body["columns"]
    assert "0123" in body["unmatched_keys"]
    assert body["duplicate_keys"] == ["AB1"]


def test_preview_never_changes_the_source_tables(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    before = [
        logged_client.get(f"/api/v1/datasets/{d['id']}/versions").json() for d in (left, right)
    ]
    _preview(logged_client, left["id"], right["id"], duplicates="all")
    after = [
        logged_client.get(f"/api/v1/datasets/{d['id']}/versions").json() for d in (left, right)
    ]
    assert before == after
    assert logged_client.get(f"/api/v1/datasets/{left['id']}").json()["row_count"] == 5


def test_duplicates_all_expands_rows_and_error_policy_refuses(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    expanded = _preview(logged_client, left["id"], right["id"], duplicates="all").json()
    assert expanded["output_rows"] == 6  # 5 linhas da consulta, AB1 gera duas
    refused = _preview(logged_client, left["id"], right["id"], duplicates="error")
    assert refused.status_code == 422
    assert "múltiplas correspondências" in refused.text


def test_conflicting_return_name_gets_suffix(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    body = _preview(
        logged_client,
        left["id"],
        right["id"],
        return_columns=["SYN-Código"],
    ).json()
    assert "SYN-Código (direita)" in body["columns"]


def test_unknown_column_is_a_rule_error(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    resp = _preview(logged_client, left["id"], right["id"], left_keys=["Nope"])
    assert resp.status_code == 422


def test_output_limit_refuses_instead_of_truncating(
    logged_client: TestClient, storage_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(crossing, "MAX_OUTPUT_ROWS", 3)
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    resp = _preview(logged_client, left["id"], right["id"], duplicates="all")
    assert resp.status_code == 422
    assert "passa de 3 linhas" in resp.text


def test_sample_is_limited(logged_client: TestClient, storage_settings: Settings) -> None:
    left = _import(logged_client, "SYN-consulta.csv", CONSULTA)
    right = _import(logged_client, "SYN-busca.csv", BUSCA)
    resp = logged_client.post(
        "/api/v1/crossing/lookup/preview?sample=2",
        json={
            "left_id": left["id"],
            "right_id": right["id"],
            "left_keys": ["SYN-Código"],
            "right_keys": ["SYN-Código"],
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["sample"]) == 2

