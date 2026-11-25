"""Fase 3: expansão das fórmulas (dados sintéticos). Sem eval; Decimal; erros explícitos."""

from __future__ import annotations

from engiflow_api.domain.formula import compile_formula, evaluate_row

ROW: dict[str, str | None] = {
    "Qtd": "4",
    "Preço": "2,5",
    "Nome": "  ana   maria ",
    "Vazio": "",
    "Zero": "0",
}
COLUMNS = list(ROW)


def _eval(source: str, row: dict[str, str | None] = ROW) -> str | None:
    return evaluate_row(compile_formula(source, COLUMNS), row)


def test_lógicas_e_ou_são_estritas() -> None:
    assert _eval("E(VERDADEIRO;FALSO)") == "FALSO"
    assert _eval("OU(VERDADEIRO;FALSO)") == "VERDADEIRO"
    assert _eval("E(VERDADEIRO;VERDADEIRO)") == "VERDADEIRO"
    assert _eval("E([Qtd];VERDADEIRO)") == "#VALOR!"  # número não vira verdadeiro
    assert _eval("OU()") == "#VALOR!"


def test_seerro_trata_só_erros_explícitos() -> None:
    assert _eval("SEERRO([Qtd]/0;0)") == "0"
    assert _eval("SEERRO([Vazio]+1;9)") == "9"  # vazio em conta é erro explícito
    assert _eval("SEERRO([Qtd]+1;9)") == "5"  # sem erro: valor preservado
    assert _eval("SEERRO([Qtd]/0;[Qtd])") == "4"
    unknown_qtd = {**ROW, "Qtd": None}
    # Referência direta a desconhecido: o valor (desconhecido) é preservado, não vira o alternativo.
    assert _eval("SEERRO([Qtd];0)", unknown_qtd) is None
    # Aritmética sobre desconhecido gera #DESCONHECIDO! explícito; SEERRO o troca só se pedido.
    assert _eval("SEERRO([Qtd]+1;0)", unknown_qtd) == "0"


def test_arred_meio_para_cima_com_decimal_sem_float() -> None:
    assert _eval("ARRED(2,345;2)") == "2.35"
    assert _eval("ARRED(-2,5;0)") == "-3"  # meio afastado de zero, como o Excel
    assert _eval("ARRED(2,5;0)") == "3"
    assert _eval("ARRED(0,1+0,2;1)") == "0.3"
    assert _eval("ARRED(1234;-2)") == "1200"
    assert _eval("ARRED(1,5;2,5)") == "#VALOR!"  # casas precisa ser inteiro


def test_abs_e_erros_propagados() -> None:
    assert _eval("ABS(-7,25)") == "7.25"
    assert _eval("ABS([Vazio])") == "#VAZIO!"


def test_arrumar_remove_espaços_das_pontas_e_repetidos() -> None:
    assert _eval("ARRUMAR([Nome])") == "ana maria"
    assert _eval('ARRUMAR("  a   b  ")') == "a b"


def test_num_caract_conta_caracteres() -> None:
    assert _eval('NUM.CARACT("abc")') == "3"
    assert _eval("NUM.CARACT([Nome])") == str(len("  ana   maria "))


def test_aliases_em_português_completo() -> None:
    assert _eval("MÍNIMO([Qtd];[Preço])") == "2.5"
    assert _eval("MÁXIMO([Qtd];[Preço])") == "4"
    assert _eval("CONTAGEM([Qtd];[Vazio])") == "1"
    assert _eval('CONCATENAR("a";"b")') == "ab"
    assert _eval('MAIÚSCULA("ab")') == "AB"
    assert _eval('MINÚSCULA("AB")') == "ab"


def test_funções_existentes_continuam_iguais() -> None:
    assert _eval("SOMA([Qtd];[Preço])") == "6.5"
    assert _eval('SE([Qtd]>3;"alto";"baixo")') == "alto"
    assert _eval('ESQUERDA("abcdef";2)') == "ab"


def test_erro_de_sintaxe_em_função_desconhecida_fica_explicito() -> None:
    assert _eval("FUNCAOINEXISTENTE(1)") == "#SINTAXE!"
