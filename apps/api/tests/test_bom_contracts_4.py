"""Fase 4: contratos internos do BOM batem com as respostas reais da API (forma e chaves)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.application import bom_contracts as c
from engiflow_api.core.config import Settings

CSV = (
    "Código pai;Código;Descrição;Qtd;Unidade;Revisão\n"
    ";TOP-CT;Topo contrato;1;UN;A\n"
    "TOP-CT;SUB-CT;Subconjunto;2;UN;A\n"
    "SUB-CT;CMP-CT-007;Componente com zero;4;UN;A\n"
    "SUB-CT;CMP-CT-7;Componente sem zero;1;KG;\n"
).encode()
MAPPING = {
    "parent_code": "Código pai",
    "child_code": "Código",
    "description": "Descrição",
    "qty": "Qtd",
    "unit": "Unidade",
    "rev": "Revisão",
}


def _keys(cls: Any) -> set[str]:
    return set(cls.__annotations__)


def _created(client: TestClient) -> dict[str, Any]:
    name = f"SYN-ct-{uuid.uuid4().hex[:6]}"
    ds = client.post("/api/v1/datasets", files={"file": (f"{name}.csv", CSV, "text/csv")}).json()[
        "dataset"
    ]
    resp = client.post(
        "/api/v1/bom/structures",
        json={
            "name": f"BOM {name}",
            "dataset_id": ds["id"],
            "mapping": MAPPING,
            "mode": "explicit",
        },
    )
    assert resp.status_code == 201, resp.text
    result: dict[str, Any] = resp.json()
    return result


def test_contrato_de_estrutura_e_revisao(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    body = _created(logged_client)
    structure = body["structure"]
    assert _keys(c.StructureContract) == set(structure)
    assert all(_keys(c.RevisionContract) == set(r) for r in structure["revisions"])


def test_contrato_de_componente_preserva_zero_a_esquerda(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    body = _created(logged_client)
    lines = logged_client.get(f"/api/v1/bom/revisions/{body['revision_id']}/lines").json()["lines"]
    assert all(set(line) == _keys(c.ComponentLineContract) for line in lines)
    codes = {line["child"] for line in lines}
    assert {"CMP-CT-007", "CMP-CT-7"} <= codes  # códigos distintos, zeros preservados


def test_contrato_de_explosao_validacao_comparacao_e_kit(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    body = _created(logged_client)
    rid = body["revision_id"]
    explosion = logged_client.post(
        f"/api/v1/bom/revisions/{rid}/explode", json={"root": "TOP-CT", "vehicles": "3"}
    ).json()
    assert set(explosion) == _keys(c.ExplosionContract)
    assert all(
        set(item) == _keys(c.ConsolidatedQuantityContract) for item in explosion["consolidated"]
    )

    validation = logged_client.get(f"/api/v1/bom/revisions/{rid}/validate").json()
    assert set(validation) == _keys(c.ValidationResultContract)
    assert all(set(issue) == _keys(c.IssueContract) for issue in validation["issues"])

    comparison = logged_client.post(
        "/api/v1/bom/compare", json={"revision_a": rid, "revision_b": rid}
    ).json()
    assert set(comparison) == _keys(c.ComparisonContract)

    kit = logged_client.post(
        f"/api/v1/bom/structures/{body['structure']['id']}/kits",
        json={"name": "Kit contrato", "parts": [{"code": "SUB-CT", "qty": "1"}]},
    ).json()
    assert set(kit) == _keys(c.KitContract)
    materials = logged_client.post(
        f"/api/v1/bom/revisions/{rid}/kit-calc",
        json={"parts": [{"code": "SUB-CT", "qty": "1"}], "vehicles": "1", "lot": "1"},
    ).json()
    assert set(materials) == _keys(c.KitMaterialsContract)
    assert c.CONTRACT_VERSION == 1
