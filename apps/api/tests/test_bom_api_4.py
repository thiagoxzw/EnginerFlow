"""Fase 4: BOM Manager pela API (importação, revisões, cálculos, cruzamento, kits, exportações).

Dados sintéticos apenas (SYN-* e códigos BOM-SYN). Cada teste cria estruturas com nomes únicos.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

MAPPING = {
    "parent_code": "Código pai",
    "child_code": "Código",
    "description": "Descrição",
    "qty": "Qtd",
    "unit": "Unidade",
    "rev": "Revisão",
}

BOM_CSV = (
    "Código pai;Código;Descrição;Qtd;Unidade;Revisão\n"
    ";ONIBUS-SYN-EV;Ônibus elétrico sintético;1;UN;A\n"
    "ONIBUS-SYN-EV;CONJ-SYN-TRAC;Conjunto de tração;2;UN;A\n"
    "ONIBUS-SYN-EV;CONJ-SYN-BAT;Conjunto de baterias;1;UN;A\n"
    "CONJ-SYN-TRAC;COMP-SYN-MOT;Motor sintético;4;UN;B\n"
    "CONJ-SYN-TRAC;PARAF-SYN-M8;Parafuso M8;0,5;KG;\n"
    "CONJ-SYN-TRAC;007-SYN-CABO;Cabo com zero à esquerda;3;M;\n"
    "CONJ-SYN-BAT;COMP-SYN-MOT;Motor sintético;1;UN;B\n"
    "CONJ-SYN-BAT;PARAF-SYN-M8;Parafuso M8;2;UN;\n"
).encode()

CADASTRO_CSV = (
    "Código;Descrição;Unidade\n"
    "COMP-SYN-MOT;Motor sintético;UN\n"
    "PARAF-SYN-M8;Parafuso M8;KG\n"
    "PARAF-SYN-M8;Parafuso M8 (duplicado);UN\n"
    "CONJ-SYN-BAT;Conjunto de baterias;UN\n"
).encode()


def _import(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (f"{name}.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _structure(
    client: TestClient, mapping: dict[str, str] | None = None, data: bytes = BOM_CSV
) -> dict[str, Any]:
    ds = _import(client, _unique("SYN-bom"), data)
    resp = client.post(
        "/api/v1/bom/structures",
        json={
            "name": _unique("BOM SYN onibus"),
            "dataset_id": ds["id"],
            "mapping": mapping or MAPPING,
            "mode": "explicit",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _lines(client: TestClient, revision_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = client.get(f"/api/v1/bom/revisions/{revision_id}/lines").json()[
        "lines"
    ]
    return result


def test_preview_nao_grava_e_mostra_contagens(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client, _unique("SYN-prev"), BOM_CSV)
    resp = logged_client.post(
        "/api/v1/bom/preview", json={"dataset_id": ds["id"], "mapping": MAPPING, "mode": "explicit"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["line_count"] == 8
    assert body["roots"] == ["ONIBUS-SYN-EV"]
    assert body["issue_counts"].get("erro", 0) == 0


def test_mapeamento_sem_campos_obrigatorios_e_recusado(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client, _unique("SYN-mapa"), BOM_CSV)
    resp = logged_client.post(
        "/api/v1/bom/preview",
        json={"dataset_id": ds["id"], "mapping": {"child_code": "Código"}, "mode": "explicit"},
    )
    assert resp.status_code in (400, 422), resp.text


def test_importacao_preserva_zero_a_esquerda_e_texto_da_quantidade(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    lines = _lines(logged_client, created["revision_id"])
    cabo = next(line for line in lines if line["child"] == "007-SYN-CABO")
    assert cabo["child"] == "007-SYN-CABO"
    parafuso = next(
        line for line in lines if line["child"] == "PARAF-SYN-M8" and line["unit"] == "KG"
    )
    assert parafuso["qty"] == "0,5"  # texto original preservado
    assert len(lines) == 8


def test_explosao_calcula_quantidades_por_veiculo(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    rid = created["revision_id"]
    body = logged_client.post(
        f"/api/v1/bom/revisions/{rid}/explode", json={"root": "ONIBUS-SYN-EV", "vehicles": "10"}
    ).json()
    totals = {(c["code"], c["unit"]): Decimal(c["qty"]) for c in body["consolidated"]}
    # Motor: 2 tração × 4 + 1 bateria × 1 = 9 por veículo → 90 para 10 veículos.
    assert totals[("COMP-SYN-MOT", "UN")] == Decimal(90)
    # Parafuso em KG e UN não é somado.
    assert totals[("PARAF-SYN-M8", "KG")] == Decimal(10)  # 0,5 × 2 × 10
    assert totals[("PARAF-SYN-M8", "UN")] == Decimal(20)
    assert body["occurrences"]["COMP-SYN-MOT"] == 2


def test_edicao_cria_nova_revisao_preserva_anterior_e_desfaz(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    base_id = created["revision_id"]
    base_lines = _lines(logged_client, base_id)
    structure_id = created["structure"]["id"]

    edited = logged_client.post(
        f"/api/v1/bom/revisions/{base_id}/edits",
        json={"edits": [{"op": "set_qty", "line_no": 4, "qty": "6"}]},
    )
    assert edited.status_code == 201, edited.text
    new_id = edited.json()["revision"]["id"]
    assert new_id != base_id
    assert _lines(logged_client, base_id) == base_lines  # revisão anterior intacta
    new_qty = next(line for line in _lines(logged_client, new_id) if line["line_no"] == 4)["qty"]
    assert new_qty == "6"

    undo = logged_client.post(
        f"/api/v1/bom/structures/{structure_id}/current", json={"revision_id": base_id}
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["current_revision_id"] == base_id
    redo = logged_client.post(
        f"/api/v1/bom/structures/{structure_id}/current", json={"revision_id": new_id}
    )
    assert redo.json()["current_revision_id"] == new_id


def test_edicao_que_cria_ciclo_e_recusada(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    rid = created["revision_id"]
    resp = logged_client.post(
        f"/api/v1/bom/revisions/{rid}/edits",
        json={
            "edits": [
                {"op": "add_line", "parent": "CONJ-SYN-BAT", "child": "ONIBUS-SYN-EV", "qty": "1"}
            ]
        },
    )
    assert resp.status_code in (400, 422), resp.text
    assert "circular" in resp.text


def test_comparacao_entre_revisoes_detecta_quantidade_alterada(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    base_id = created["revision_id"]
    edited = logged_client.post(
        f"/api/v1/bom/revisions/{base_id}/edits",
        json={"edits": [{"op": "set_qty", "line_no": 4, "qty": "6"}]},
    ).json()
    result = logged_client.post(
        "/api/v1/bom/compare", json={"revision_a": base_id, "revision_b": edited["revision"]["id"]}
    ).json()
    kinds = {(c["kind"], c["child"]) for c in result["changes"]}
    assert ("quantidade", "COMP-SYN-MOT") in kinds
    assert result["counts"]["identicos"] > 0


def test_validacao_aponta_quantidade_invalida_sem_alterar(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    bad = BOM_CSV.replace(
        b"CONJ-SYN-BAT;PARAF-SYN-M8;Parafuso M8;2;UN;",
        b"CONJ-SYN-BAT;PARAF-SYN-M8;Parafuso M8;abc;UN;",
    )
    created = _structure(logged_client, data=bad)
    result = logged_client.get(f"/api/v1/bom/revisions/{created['revision_id']}/validate").json()
    rules = {i["rule"] for i in result["issues"]}
    assert "quantidade_invalida" in rules
    assert len(_lines(logged_client, created["revision_id"])) == 8


def test_cruzamento_com_cadastro_sinaliza_sem_cadastro_e_multiplas(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    cad = _import(logged_client, _unique("SYN-cadastro"), CADASTRO_CSV)
    result = logged_client.post(
        f"/api/v1/bom/revisions/{created['revision_id']}/cross",
        json={
            "cadastro_dataset_id": cad["id"],
            "key_column": "Código",
            "description_column": "Descrição",
            "unit_column": "Unidade",
            "key_mode": "exato",
        },
    ).json()
    status = {i["code"]: i["status"] for i in result["items"]}
    assert status["COMP-SYN-MOT"] == "encontrado"
    assert status["PARAF-SYN-M8"] == "multiplas_correspondencias"
    assert status["007-SYN-CABO"] == "sem_cadastro"
    cabo = next(i for i in result["items"] if i["code"] == "007-SYN-CABO")
    assert cabo["equivalent_candidates"] == []  # sem candidato por descrição: nada sugerido


def test_kit_calcula_materiais_por_veiculo_e_lote(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    sid = created["structure"]["id"]
    rid = created["revision_id"]
    kit = logged_client.post(
        f"/api/v1/bom/structures/{sid}/kits",
        json={"name": "Kit tração", "parts": [{"code": "CONJ-SYN-TRAC", "qty": "1"}]},
    )
    assert kit.status_code == 201, kit.text
    listed = logged_client.get(f"/api/v1/bom/structures/{sid}/kits").json()
    assert [k["name"] for k in listed] == ["Kit tração"]
    calc = logged_client.post(
        f"/api/v1/bom/revisions/{rid}/kit-calc",
        json={"parts": [{"code": "CONJ-SYN-TRAC", "qty": "1"}], "vehicles": "10", "lot": "2"},
    ).json()
    materials = {(m["code"], m["unit"]): Decimal(m["qty"]) for m in calc["materials"]}
    assert materials[("COMP-SYN-MOT", "UN")] == Decimal(80)  # 4 por kit × 2 kits × 10 veículos


def test_exportacoes_xlsx_csv_e_hierarquia(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    rid = created["revision_id"]
    xlsx = logged_client.get(
        f"/api/v1/bom/revisions/{rid}/export", params={"kind": "lines", "fmt": "xlsx"}
    )
    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    csv = logged_client.get(
        f"/api/v1/bom/revisions/{rid}/export",
        params={"kind": "hierarchy", "fmt": "csv", "root": "ONIBUS-SYN-EV"},
    )
    assert csv.status_code == 200
    assert "COMP-SYN-MOT" in csv.text
    cons = logged_client.get(
        f"/api/v1/bom/revisions/{rid}/export",
        params={"kind": "consolidated", "fmt": "csv", "root": "ONIBUS-SYN-EV", "vehicles": "10"},
    )
    assert "90" in cons.text


def test_modo_por_nivel_infere_pai_e_marca_como_inferido(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    level_csv = (
        "Nível;Código;Descrição;Qtd;Unidade\n"
        "1;ONIBUS-SYN-LV;Ônibus;1;UN\n"
        "2;CONJ-SYN-LV;Conjunto;1;UN\n"
        "3;COMP-SYN-LV;Componente;5;UN\n"
    ).encode()
    ds = _import(logged_client, _unique("SYN-nivel"), level_csv)
    body = logged_client.post(
        "/api/v1/bom/preview",
        json={
            "dataset_id": ds["id"],
            "mapping": {"level": "Nível", "child_code": "Código", "qty": "Qtd", "unit": "Unidade"},
            "mode": "level",
        },
    ).json()
    assert body["inferred_parents"] == 2
    assert body["roots"] == ["ONIBUS-SYN-LV"]


def test_duplicacao_completa_pela_api_cria_nova_revisao_com_descendentes(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    base_id = created["revision_id"]
    edited = logged_client.post(
        f"/api/v1/bom/revisions/{base_id}/edits",
        json={
            "edits": [
                {"op": "duplicate_subtree", "code": "CONJ-SYN-TRAC", "new_code": "CONJ-SYN-TRAC-B"}
            ]
        },
    )
    assert edited.status_code == 201, edited.text
    new_id = edited.json()["revision"]["id"]
    body = logged_client.post(
        f"/api/v1/bom/revisions/{new_id}/explode", json={"root": "ONIBUS-SYN-EV", "vehicles": "1"}
    ).json()
    motors = {c["code"]: Decimal(c["qty"]) for c in body["consolidated"]}
    # Tração original (2×4=8) + cópia da tração (2×4=8) + bateria (1×1=1).
    assert motors["COMP-SYN-MOT"] == Decimal(17)
    # A revisão anterior não muda.
    base = logged_client.post(
        f"/api/v1/bom/revisions/{base_id}/explode", json={"root": "ONIBUS-SYN-EV", "vehicles": "1"}
    ).json()
    assert {c["code"]: Decimal(c["qty"]) for c in base["consolidated"]}["COMP-SYN-MOT"] == Decimal(
        9
    )


def test_kit_importado_de_tabela_tem_previa_erros_e_calculo_de_folhas(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    sid = created["structure"]["id"]
    rid = created["revision_id"]
    kit_csv = (
        "Código;Quantidade;Unidade;Descrição\n"
        "COMP-SYN-MOT;2;UN;Motor sintético\n"
        "PARAF-SYN-M8;3;UN;Parafuso M8\n"
        "PARAF-SYN-M8;1;UN;Parafuso M8 (mesmo código, somado)\n"
    ).encode()
    ds = _import(logged_client, _unique("SYN-kit"), kit_csv)
    mapping = {"code": "Código", "qty": "Quantidade", "unit": "Unidade", "description": "Descrição"}
    preview = logged_client.post(
        f"/api/v1/bom/structures/{sid}/kits/import/preview",
        json={"dataset_id": ds["id"], "mapping": mapping},
    ).json()
    parts = {p["code"]: p for p in preview["parts"]}
    assert parts["PARAF-SYN-M8"]["qty"] == "4"  # somado
    assert parts["COMP-SYN-MOT"]["unit"] == "UN"
    severities = {i["severity"] for i in preview["issues"]}
    assert severities == {"informação"}  # só a soma; nenhum código inválido nesta tabela

    created_kit = logged_client.post(
        f"/api/v1/bom/structures/{sid}/kits/import",
        json={"name": "Kit importado SYN", "dataset_id": ds["id"], "mapping": mapping},
    )
    assert created_kit.status_code == 201, created_kit.text
    calc = logged_client.post(
        f"/api/v1/bom/revisions/{rid}/kit-calc",
        json={"parts": [p for p in created_kit.json()["parts"]], "vehicles": "10", "lot": "1"},
    ).json()
    materials = {(m["code"], m["unit"]): Decimal(m["qty"]) for m in calc["materials"]}
    # Peças folha entram por si: motor 2 × 10 = 20; parafuso 4 × 10 = 40.
    assert materials[("COMP-SYN-MOT", "UN")] == Decimal(20)
    assert materials[("PARAF-SYN-M8", "UN")] == Decimal(40)


def test_kit_importado_com_erro_nao_e_criado(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    sid = created["structure"]["id"]
    bad_csv = "Código;Quantidade\nCOMP-SYN-MOT;abc\n".encode()
    ds = _import(logged_client, _unique("SYN-kit-ruim"), bad_csv)
    resp = logged_client.post(
        f"/api/v1/bom/structures/{sid}/kits/import",
        json={
            "name": "Kit ruim",
            "dataset_id": ds["id"],
            "mapping": {"code": "Código", "qty": "Quantidade"},
        },
    )
    assert resp.status_code in (400, 422), resp.text
    listed = logged_client.get(f"/api/v1/bom/structures/{sid}/kits").json()
    assert all(k["name"] != "Kit ruim" for k in listed)


def test_kit_com_subconjunto_conta_componentes_e_nao_o_proprio_conjunto(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    rid = created["revision_id"]
    calc = logged_client.post(
        f"/api/v1/bom/revisions/{rid}/kit-calc",
        json={"parts": [{"code": "CONJ-SYN-TRAC", "qty": "1"}], "vehicles": "1", "lot": "1"},
    ).json()
    codes = {m["code"] for m in calc["materials"]}
    assert "CONJ-SYN-TRAC" not in codes
    assert "COMP-SYN-MOT" in codes


def test_kit_com_codigo_fora_da_estrutura_e_recusado(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    created = _structure(logged_client)
    sid = created["structure"]["id"]
    ds = _import(
        logged_client, _unique("SYN-kit-fora"), "Código;Quantidade\nNAO-EXISTE-SYN;1\n".encode()
    )
    resp = logged_client.post(
        f"/api/v1/bom/structures/{sid}/kits/import",
        json={
            "name": "Kit fora",
            "dataset_id": ds["id"],
            "mapping": {"code": "Código", "qty": "Quantidade"},
        },
    )
    assert resp.status_code in (400, 422), resp.text
