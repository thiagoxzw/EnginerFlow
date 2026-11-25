"""Fase 4: núcleo do BOM Manager (funções puras). Dados sintéticos apenas (BOM-SYN-*)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from engiflow_api.domain.bom import (
    BomError,
    BomLine,
    compare,
    explode,
    find_cycles,
    kit_requirements,
    validate,
)


def L(
    n: int,
    parent: str | None,
    child: str | None,
    qty: str | None = "1",
    unit: str | None = "UN",
    **kw: str | int | None,
) -> BomLine:
    return BomLine(line_no=n, parent=parent, child=child, qty_raw=qty, unit=unit, **kw)  # type: ignore[arg-type]


# Estrutura sintética de ônibus elétrico (códigos fictícios).
BUS = [
    L(2, None, "BUS-SYN-EV", "1", "UN", description="Ônibus elétrico sintético"),
    L(3, "BUS-SYN-EV", "CONJ-SYN-TRAC", "2", "UN", description="Conjunto de tração"),
    L(4, "BUS-SYN-EV", "CONJ-SYN-BAT", "1", "UN", description="Conjunto de baterias"),
    L(5, "CONJ-SYN-TRAC", "COMP-SYN-MOT", "4", "UN", description="Motor sintético"),
    L(6, "CONJ-SYN-TRAC", "PARAF-SYN-M8", "0,5", "KG", description="Parafuso M8"),
    L(7, "CONJ-SYN-BAT", "COMP-SYN-MOT", "1", "UN", description="Motor sintético"),
    L(8, "CONJ-SYN-BAT", "PARAF-SYN-M8", "2", "UN", description="Parafuso M8"),
]


def test_exemplo_do_pedido_dois_conjuntos_quatro_componentes_por_veiculo() -> None:
    simple = [
        L(1, None, "VEIC-SYN"),
        L(2, "VEIC-SYN", "CONJ-SYN-A", "2"),
        L(3, "CONJ-SYN-A", "COMP-SYN-B", "4"),
    ]
    one = explode(simple, "VEIC-SYN", Decimal(1))
    assert one.consolidated[("COMP-SYN-B", "UN")] == Decimal(8)
    ten = explode(simple, "VEIC-SYN", Decimal(10))
    assert ten.consolidated[("COMP-SYN-B", "UN")] == Decimal(80)
    assert (
        ten.occurrences["COMP-SYN-B"] == 1
    )  # uma ocorrência por posição de A (duas posições = duas)


def test_explosao_soma_caminhos_diferentes_do_mesmo_componente() -> None:
    result = explode(BUS, "BUS-SYN-EV", Decimal(10))
    # Motor: 2 tração × 4 + 1 bateria × 1 = 9 por veículo → 90.
    assert result.consolidated[("COMP-SYN-MOT", "UN")] == Decimal(90)
    # Parafuso M8 em unidades diferentes: não é somado entre KG e UN.
    assert result.consolidated[("PARAF-SYN-M8", "KG")] == Decimal("10.0")  # 0,5 × 2 × 10
    assert result.consolidated[("PARAF-SYN-M8", "UN")] == Decimal(20)  # 2 × 1 × 10
    assert any("unidades diferentes" in w for w in result.warnings)


def test_ocorrencias_contam_aparicoes_na_estrutura_nao_codigos() -> None:
    result = explode(BUS, "BUS-SYN-EV", Decimal(1))
    assert result.occurrences["COMP-SYN-MOT"] == 2  # aparece sob tração e sob bateria
    assert result.occurrences["PARAF-SYN-M8"] == 2


def test_ciclo_e_detectado_e_explosao_e_recusada() -> None:
    cyc = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "A-SYN"),
        L(3, "A-SYN", "B-SYN"),
        L(4, "B-SYN", "A-SYN"),
    ]
    assert find_cycles(cyc)
    with pytest.raises(BomError, match="Ciclo detectado"):
        explode(cyc, "TOPO-SYN", Decimal(1))


def test_raiz_inexistente_e_quantidade_de_veiculos_invalida() -> None:
    with pytest.raises(BomError, match="não existe"):
        explode(BUS, "INEXISTENTE-SYN", Decimal(1))
    with pytest.raises(BomError, match="maior que zero"):
        explode(BUS, "BUS-SYN-EV", Decimal(0))


def test_quantidade_invalida_fica_fora_do_calculo_com_aviso() -> None:
    lines = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "X-SYN", "abc"),
        L(3, "TOPO-SYN", "Y-SYN", "3"),
    ]
    result = explode(lines, "TOPO-SYN", Decimal(2))
    assert ("X-SYN", "UN") not in result.consolidated
    assert result.consolidated[("Y-SYN", "UN")] == Decimal(6)
    assert result.invalid_lines == [2]


def test_codigos_com_zero_a_esquerda_sao_distintos() -> None:
    lines = [L(1, None, "TOPO-SYN"), L(2, "TOPO-SYN", "007"), L(3, "TOPO-SYN", "7")]
    result = explode(lines, "TOPO-SYN", Decimal(1))
    assert ("007", "UN") in result.consolidated
    assert ("7", "UN") in result.consolidated


def test_kit_soma_subconjuntos_por_kit_e_lote() -> None:
    total = kit_requirements(
        BUS, [("CONJ-SYN-TRAC", Decimal(1))], vehicles=Decimal(10), lot=Decimal(2)
    )
    # Tração por kit: motor 4, parafuso 0,5 KG. Lote 2 × 10 veículos = 20 kits.
    assert total[("COMP-SYN-MOT", "UN")] == Decimal(80)
    assert total[("PARAF-SYN-M8", "KG")] == Decimal("10.0")


def test_comparacao_identifica_quantidade_transferencia_adicao_e_remocao() -> None:
    rev_b = [
        L(2, None, "BUS-SYN-EV", "1", "UN", description="Ônibus elétrico sintético"),
        L(3, "BUS-SYN-EV", "CONJ-SYN-TRAC", "2", "UN"),
        L(4, "BUS-SYN-EV", "CONJ-SYN-BAT", "1", "UN"),
        L(
            5, "CONJ-SYN-TRAC", "COMP-SYN-MOT", "6", "UN", description="Motor sintético"
        ),  # quantidade alterada
        L(6, "CONJ-SYN-TRAC", "PARAF-SYN-M8", "0,5", "KG"),
        L(7, "CONJ-SYN-BAT", "COMP-SYN-MOT", "1", "UN"),
        # Parafuso UN sob bateria deixa de existir (não há par com a mesma quantidade): removido.
        L(8, "CONJ-SYN-TRAC", "NOVO-SYN-SENSOR", "1", "UN"),  # adicionado
    ]
    result = compare(BUS, rev_b)
    kinds = {(c.kind, c.child) for c in result.changes}
    assert ("quantidade", "COMP-SYN-MOT") in kinds
    assert ("adicionado", "NOVO-SYN-SENSOR") in kinds
    assert ("removido", "PARAF-SYN-M8") in kinds
    assert result.counts()["identicos"] >= 1


def test_componente_transferido_entre_conjuntos_com_mesma_quantidade() -> None:
    before = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "CONJ-SYN-X", "1"),
        L(3, "TOPO-SYN", "CONJ-SYN-Y", "1"),
        L(4, "CONJ-SYN-X", "SENSOR-SYN", "3"),
    ]
    after = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "CONJ-SYN-X", "1"),
        L(3, "TOPO-SYN", "CONJ-SYN-Y", "1"),
        L(4, "CONJ-SYN-Y", "SENSOR-SYN", "3"),  # mudou de X para Y, mesma quantidade
    ]
    result = compare(before, after)
    transferred = [c for c in result.changes if c.kind == "transferido"]
    assert [c.child for c in transferred] == ["SENSOR-SYN"]
    assert not [c for c in result.changes if c.kind in ("adicionado", "removido")]


def test_comparacao_de_identicas_nao_gera_alteracoes() -> None:
    result = compare(BUS, list(BUS))
    assert result.changes == []
    assert result.identical > 0


def test_comparacao_nao_trata_mesmo_codigo_em_outro_pai_como_duplicata() -> None:
    result = compare(BUS, list(BUS))
    assert not result.unmatched_added and not result.unmatched_removed


def test_possivel_troca_de_codigo_fica_pendente_nao_automatica() -> None:
    before = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "OLD-SYN", "1", description="Bucha sintética"),
    ]
    after = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "NEW-SYN", "1", description="Bucha sintética"),
    ]
    result = compare(before, after)
    assert result.pending_code_changes == [("OLD-SYN", "NEW-SYN")]
    assert not any(c.kind == "alteracao_codigo" for c in result.changes)


def test_validacao_aponta_erros_sem_alterar_dados() -> None:
    lines = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", None, "1"),  # sem código
        L(3, "TOPO-SYN", "A-SYN", "abc"),  # quantidade inválida
        L(4, "TOPO-SYN", "B-SYN", "-2"),  # negativa
        L(5, "TOPO-SYN", "C-SYN", "0"),  # zerada
        L(6, "FANTASMA-SYN", "D-SYN", "1"),  # pai inexistente
        L(7, "TOPO-SYN", "E-SYN", "1", description=None),  # sem descrição
    ]
    rules = {(i.rule, i.severity) for i in validate(lines)}
    assert ("sem_codigo", "erro") in rules
    assert ("quantidade_invalida", "erro") in rules
    assert ("quantidade_negativa", "erro") in rules
    assert ("quantidade_zerada", "alerta") in rules
    assert ("pai_inexistente", "erro") in rules
    assert ("sem_descricao", "alerta") in rules
    assert len(lines) == 7  # nada foi alterado


def test_validacao_detecta_ciclo_orfao_unidade_revisao_e_descricao() -> None:
    lines = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "P-SYN", "1", unit="UN", rev="A", description="Porca"),
        L(3, "TOPO-SYN", "P-SYN", "1", unit="KG", rev="B", description="Porca sextavada"),
        L(4, "NAO-DEFINIDO-SYN", "ORFAO-SYN", "1"),
        L(5, "ORFAO-SYN", "X-SYN", "1"),
        L(6, "X-SYN", "Y-SYN", "1"),
        L(7, "Y-SYN", "X-SYN", "1"),
    ]
    rules = {i.rule for i in validate(lines)}
    assert "ciclo" in rules
    assert "orfao" in rules
    assert "unidade_incompativel" in rules
    assert "revisao_conflitante" in rules
    assert "descricao_divergente" in rules
    assert "duplicidade_no_conjunto" in rules


def test_nivel_sem_pai_no_modo_por_nivel() -> None:
    lines = [L(1, None, "TOPO-SYN", level=1), L(2, None, "SOLTO-SYN", level=2)]
    rules = {i.rule for i in validate(lines, mode="level")}
    assert "nivel_sem_pai" in rules


def test_duplicacao_completa_copia_descendentes_com_codigos_internos_proprios() -> None:
    from engiflow_api.domain.bom import duplicate_subtree

    lines = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "SUB-SYN", "2"),
        L(3, "SUB-SYN", "MOT-SYN", "4"),
        L(4, "SUB-SYN", "SUBSUB-SYN", "3"),
        L(5, "SUBSUB-SYN", "PARAF-SYN", "5"),
    ]
    added, mapping = duplicate_subtree(lines, "SUB-SYN", "SUB2-SYN", "-CP", next_no=6)
    assert mapping == {"SUB-SYN": "SUB2-SYN", "SUBSUB-SYN": "SUBSUB-SYN-CP"}
    edges = {(a.parent, a.child, a.qty_raw) for a in added}
    assert edges == {
        ("TOPO-SYN", "SUB2-SYN", "2"),  # conjunto no mesmo pai, mesma quantidade
        ("SUB2-SYN", "MOT-SYN", "4"),  # folha mantém o código
        ("SUB2-SYN", "SUBSUB-SYN-CP", "3"),  # subconjunto interno com código próprio
        ("SUBSUB-SYN-CP", "PARAF-SYN", "5"),
    }
    combined = [*lines, *added]
    assert find_cycles(combined) == []
    result = explode(combined, "TOPO-SYN", Decimal(1))
    # Parafuso: original (2×3×5=30) + cópia (2×3×5=30) = 60.
    assert result.consolidated[("PARAF-SYN", "UN")] == Decimal(60)
    assert result.consolidated[("MOT-SYN", "UN")] == Decimal(16)


def test_duplicacao_completa_recusa_codigo_existente_e_sufixo_que_colide() -> None:
    import pytest as _pytest

    from engiflow_api.domain.bom import BomError, duplicate_subtree

    lines = [
        L(1, None, "TOPO-SYN"),
        L(2, "TOPO-SYN", "SUB-SYN", "2"),
        L(3, "SUB-SYN", "SUBSUB-SYN", "3"),
        L(4, "SUBSUB-SYN", "FOLHA-SYN", "1"),
    ]
    with _pytest.raises(BomError, match="já existe"):
        duplicate_subtree(lines, "SUB-SYN", "TOPO-SYN", "-CP", next_no=4)
    lines_clash = [*lines, L(5, "TOPO-SYN", "SUBSUB-SYN-CP", "1")]
    with _pytest.raises(BomError, match="já existem"):
        duplicate_subtree(lines_clash, "SUB-SYN", "SUB2-SYN", "-CP", next_no=5)
