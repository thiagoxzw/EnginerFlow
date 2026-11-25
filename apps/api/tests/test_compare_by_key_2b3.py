"""2B.3: comparação de linhas por chave e modos de valor. Dados sintéticos."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings
from engiflow_api.domain.comparison import compare, values_equal

ORIGEM = (
    "SYN-Código;SYN-Unidade;SYN-Preço\n00123;PC;1,50\n00123;CX;2\nAB1;PC;3\n;PC;4\n0123;PC;5\n"
).encode()
BUSCA = "SYN-Código;SYN-Unidade;SYN-Preço\n00123;PC;1.5\nAB1;PC;4\nNEW1;PC;9\n00123;PC;7\n".encode()


def _import(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (name, data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _body(left: str, right: str, modes: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "left_id": left,
        "right_id": right,
        "left_keys": ["SYN-Código", "SYN-Unidade"],
        "right_keys": ["SYN-Código", "SYN-Unidade"],
        "modes": modes or {},
    }


# --- Exemplos obrigatórios de semântica (valores) -------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "mode", "expected"),
    [
        # Código não é número: zeros e texto preservados em todos os modos de valor exato.
        ("007", "7", "exato", False),
        ("00123", "0123", "exato", False),
        ("007", "7", "normalizado", False),
        ("007", "7", "descricao_tecnica", False),
        # Quantidade em modo numérico: equivalência decimal.
        ("007", "7", "numerico", True),
        ("1,50", "1.5", "numerico", True),
        # Descrição técnica: dimensão e tolerância discriminam.
        ("M16X1,5", "M16X2", "descricao_tecnica", False),
        ("M16X1,5", "M16x1,5", "descricao_tecnica", True),
        ("M16X1,5", "M16X2", "normalizado", False),
        # Texto exato preserva caixa e espaços.
        ("Parafuso", "parafuso", "exato", False),
        ("Parafuso", "Parafuso ", "exato", False),
        ("Parafuso", "parafuso", "normalizado", True),
        ("Ação", "Acao", "normalizado", True),
        ("Ação", "Acao", "descricao_tecnica", False),
        # Desconhecido, vazio e zero são coisas diferentes.
        (None, "", "exato", False),
        (None, "", "numerico", False),
        ("", "0", "numerico", False),
        ("", "0", "exato", False),
        (None, None, "exato", True),
        ("", "", "exato", True),
    ],
)
def test_value_modes(a: str | None, b: str | None, mode: str, expected: bool) -> None:
    assert values_equal(a, b, mode) is expected


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="desconhecido"):
        values_equal("a", "a", "fuzzy")


# --- Classificação ---------------------------------------------------------------------------


def test_domain_classifies_each_case_with_exact_default() -> None:
    left = [["00123", "PC", "1,50"], ["00123", "CX", "2"], ["AB1", "PC", "3"], ["", "PC", "4"]]
    right = [["00123", "PC", "1.5"], ["AB1", "PC", "4"], ["NEW1", "PC", "9"], ["00123", "PC", "7"]]
    result = compare(left, right, [0, 1], [0, 1], [(2, 2, "SYN-Preço")])
    # Padrão exato: "1,50" ≠ "1.5" e "3" ≠ "4" -> ambas as linhas com chave casada são alteradas.
    assert result.counts["alterado"] == 2
    assert result.counts["idêntico"] == 0
    assert result.counts["removido"] == 1  # 00123|CX só na origem
    assert result.counts["adicionado"] == 1  # NEW1|PC só na busca
    assert result.counts["chaves_invalidas_esquerda"] == 1
    assert result.counts["chaves_duplicadas_busca"] == 1


def test_domain_numeric_mode_turns_equivalent_values_identical() -> None:
    left = [["00123", "PC", "1,50"]]
    right = [["00123", "PC", "1.5"]]
    result = compare(
        left, right, [0, 1], [0, 1], [(2, 2, "SYN-Preço")], modes={"SYN-Preço": "numerico"}
    )
    assert result.counts["idêntico"] == 1


def test_unknown_and_empty_are_reported_as_different_values() -> None:
    left: list[list[str | None]] = [["K1", None], ["K2", ""]]
    right: list[list[str | None]] = [["K1", ""], ["K2", None]]
    result = compare(left, right, [0], [0], [(1, 1, "V")])
    assert result.counts["alterado"] == 2
    values = {(row[1], row[3], row[4]) for row in result.rows}
    assert ("K1", None, "") in values  # desconhecido na origem, vazio na busca: saída preserva None


def test_keys_never_use_numeric_equivalence() -> None:
    left = [["007", "PC", "a"]]
    right = [["7", "PC", "a"]]
    result = compare(left, right, [0, 1], [0, 1], [(2, 2, "V")], modes={"V": "numerico"})
    assert result.counts["removido"] == 1
    assert result.counts["adicionado"] == 1


# --- API: modos, rastreabilidade e derivação -------------------------------------------------


def test_api_compare_preview_and_derive_keep_sources_and_record_modes(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-cmp-origem.csv", ORIGEM)
    right = _import(logged_client, "SYN-cmp-busca.csv", BUSCA)

    exact = logged_client.post(
        "/api/v1/crossing/compare/preview", json=_body(left["id"], right["id"])
    )
    assert exact.status_code == 200, exact.text
    assert exact.json()["counts"]["alterado"] == 2  # padrão exato

    body = _body(left["id"], right["id"], {"SYN-Preço": "numerico"})
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
    assert " × " in detail["name"]
    assert logged_client.get(f"/api/v1/datasets/{left['id']}").json()["row_count"] == 5


def test_api_rejects_mode_for_column_that_is_not_compared(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-cmp-origem2.csv", ORIGEM)
    right = _import(logged_client, "SYN-cmp-busca2.csv", BUSCA)
    resp = logged_client.post(
        "/api/v1/crossing/compare/preview",
        json=_body(left["id"], right["id"], {"SYN-Inexistente": "numerico"}),
    )
    assert resp.status_code in (400, 422), resp.text
