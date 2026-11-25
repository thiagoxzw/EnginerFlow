"""2B.3: rota de junção (prévia e derivação). Dados sintéticos.

Regressão: a derivação da junção devolvia 500 porque `counts` traz a cardinalidade em texto
("N:M") e a resposta exigia inteiros.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

ESQUERDA = "SYN-Código;SYN-Unidade\n00123;PC\n00123;PC\nAB1;CX\n".encode()
DIREITA = (
    "SYN-Código;SYN-Unidade;SYN-Descrição\n00123;PC;SYN parafuso\nAB1;CX;SYN arruela\n".encode()
)


def _import(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (name, data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _body(left: str, right: str) -> dict[str, Any]:
    return {
        "left_id": left,
        "right_id": right,
        "left_keys": ["SYN-Código", "SYN-Unidade"],
        "right_keys": ["SYN-Código", "SYN-Unidade"],
        "join_type": "left",
    }


def test_join_preview_reports_cardinality_and_estimate(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-junc-esq.csv", ESQUERDA)
    right = _import(logged_client, "SYN-junc-dir.csv", DIREITA)
    resp = logged_client.post("/api/v1/crossing/join/preview", json=_body(left["id"], right["id"]))
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["cardinality"] == "N:1"
    assert preview["left_rows"] == 3
    assert preview["estimated_rows"] == 3


def test_join_derive_returns_201_with_text_cardinality_in_counts(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-junc-esq2.csv", ESQUERDA)
    right = _import(logged_client, "SYN-junc-dir2.csv", DIREITA)
    resp = logged_client.post("/api/v1/crossing/join/derive", json=_body(left["id"], right["id"]))
    assert resp.status_code == 201, resp.text
    derived = resp.json()
    assert derived["row_count"] == 3
    assert derived["counts"]["cardinalidade"] == "N:1"
    assert derived["counts"]["linhas_esquerda"] == 3
    detail = logged_client.get(f"/api/v1/datasets/{derived['dataset_id']}").json()
    assert detail["source_kind"] == "derived"
