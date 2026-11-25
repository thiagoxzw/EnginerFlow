"""2B.3: comparação de linhas por chave composta. Dados sintéticos."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings
from engiflow_api.domain.comparison import compare

ORIGEM = (
    "SYN-Código;SYN-Unidade;SYN-Preço\n00123;PC;1,50\n00123;CX;2\nAB1;PC;3\n;PC;4\n0123;PC;5\n"
).encode()
BUSCA = "SYN-Código;SYN-Unidade;SYN-Preço\n00123;PC;1.5\nAB1;PC;4\nNEW1;PC;9\n00123;PC;7\n".encode()


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
    }


def test_domain_classifies_each_case() -> None:
    left = [["00123", "PC", "1,50"], ["00123", "CX", "2"], ["AB1", "PC", "3"], ["", "PC", "4"]]
    right = [["00123", "PC", "1.5"], ["AB1", "PC", "4"], ["NEW1", "PC", "9"], ["00123", "PC", "7"]]
    result = compare(left, right, [0, 1], [0, 1], [(2, 2, "SYN-Preço")])
    assert result.counts["idêntico"] == 1
    assert result.counts["removido"] == 1
    assert result.counts["alterado"] == 1
    assert result.counts["adicionado"] == 1
    assert result.counts["chaves_invalidas_esquerda"] == 1
    assert result.counts["chaves_duplicadas_busca"] == 1
    changed = [r for r in result.rows if r[0] == "alterado"]
    assert changed == [["alterado", "AB1 + PC", "SYN-Preço", "3", "4"]]


def test_decimal_equality_ignores_format_but_text_stays_exact() -> None:
    left = [["K", "1,50"], ["L", "007"]]
    right = [["K", "1.5"], ["L", "7"]]
    result = compare(left, right, [0], [0], [(1, 1, "V")])
    # Valores (não chaves): ambos são números, então valem por Decimal.
    # "1,50" = "1.5" e "007" = "7".
    # Texto que não é número mantém zeros (ver test_text_with_leading_zeros...).
    assert result.counts["idêntico"] == 2


def test_text_with_leading_zeros_is_compared_as_text_when_not_numeric() -> None:
    left = [["A1", "0123X"]]
    right = [["A1", "123X"]]
    result = compare(left, right, [0], [0], [(1, 1, "V")])
    assert result.counts["alterado"] == 1


def test_api_compare_preview_and_derive_keep_sources(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-cmp-origem.csv", ORIGEM)
    right = _import(logged_client, "SYN-cmp-busca.csv", BUSCA)
    body = _body(left["id"], right["id"])

    preview = logged_client.post("/api/v1/crossing/compare/preview", json=body)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["counts"]["idêntico"] == 1
    assert data["counts"]["removido"] == 2
    assert data["counts"]["alterado"] == 1
    assert data["counts"]["adicionado"] == 1
    assert data["difference_rows"] == 4

    derived = logged_client.post("/api/v1/crossing/compare/derive", json=body)
    assert derived.status_code == 201, derived.text
    out = derived.json()
    assert out["row_count"] == 4
    detail = logged_client.get(f"/api/v1/datasets/{out['dataset_id']}").json()
    assert detail["source_kind"] == "derived"
    assert detail["columns"] == ["tipo", "chave", "coluna", "antes", "depois"]
    assert " × " in detail["name"]  # duas origens
    assert logged_client.get(f"/api/v1/datasets/{left['id']}").json()["row_count"] == 5
