"""2B.3: fórmulas por linha (domínio puro, sem eval). Dados sintéticos."""

from __future__ import annotations

import pytest

from engiflow_api.domain.formula import (
    ERR_DIV0,
    ERR_EMPTY,
    ERR_UNKNOWN,
    ERR_VALUE,
    FormulaError,
    compile_formula,
    evaluate_row,
)

COLS = ["SYN-Código", "Qtd", "Preço", "Descrição"]


def _eval(source: str, row: dict[str, str | None]) -> str | None:
    formula = compile_formula(source, COLS)
    return evaluate_row(formula, row)


ROW: dict[str, str | None] = {
    "SYN-Código": "00123",
    "Qtd": "4",
    "Preço": "2,5",
    "Descrição": "Porca M8",
}


def test_precedence_and_parentheses() -> None:
    assert _eval("[Qtd]+[Preço]*2", ROW) == "9"
    assert _eval("([Qtd]+[Preço])*2", ROW) == "13"


def test_decimal_comma_and_exact_decimal_arithmetic() -> None:
    assert _eval("0,1+0,2", {}) == "0.3"  # sem 0.30000000000000004 de ponto flutuante
    assert _eval("[Preço]*4", ROW) == "10"


def test_division_and_division_by_zero_is_explicit() -> None:
    assert _eval("[Qtd]/8", ROW) == "0.5"
    assert _eval("[Qtd]/0", ROW) == ERR_DIV0


def test_empty_and_unknown_and_text_are_explicit_errors_not_zero() -> None:
    assert _eval("[Qtd]+1", {"Qtd": ""}) == ERR_EMPTY
    assert _eval("[Qtd]+1", {"Qtd": None}) == ERR_UNKNOWN
    assert _eval("[Descrição]*2", ROW) == ERR_VALUE


def test_functions_numeric() -> None:
    assert _eval("SOMA([Qtd];[Preço])", ROW) == "6.5"
    assert _eval("MEDIA([Qtd];[Preço])", ROW) == "3.25"
    assert _eval("MÉDIA([Qtd];[Preço])", ROW) == "3.25"  # nome sem acento é o mesmo
    assert _eval("MIN([Qtd];[Preço])", ROW) == "2.5"
    assert _eval("MAX([Qtd];[Preço])", ROW) == "4"
    assert _eval("CONTAR([Qtd];[Descrição];[Preço])", ROW) == "3"


def test_conditions_and_branch_isolation() -> None:
    assert _eval('SE([Qtd]>3;"grande";"pequeno")', ROW) == "grande"
    assert _eval('SE([Qtd]=3;"sim";"não")', ROW) == "não"
    # O ramo não escolhido com erro não contamina o resultado.
    assert _eval('SE([Qtd]>3;"ok";[Descrição]*2)', ROW) == "ok"


def test_text_functions_and_concat_keep_leading_zeros() -> None:
    assert _eval('CONCAT([SYN-Código];"-";[Descrição])', ROW) == "00123-Porca M8"
    assert _eval("MAIUSC([Descrição])", ROW) == "PORCA M8"
    assert _eval("ESQUERDA([SYN-Código];3)", ROW) == "001"
    assert _eval("DIREITA([SYN-Código];2)", ROW) == "23"


def test_reference_returns_text_unchanged() -> None:
    assert _eval("[SYN-Código]", ROW) == "00123"


@pytest.mark.parametrize(
    "source",
    [
        "",
        "[Qtd]+",
        "SOMA([Qtd]",
        "[Qtd] [Qtd]",
        "__import__('os')",
        "SOMA(1;2",
        '"sem fechar',
        "[Qtd]^2",
    ],
)
def test_invalid_syntax_is_refused(source: str) -> None:
    with pytest.raises(FormulaError):
        compile_formula(source, COLS)


def test_unknown_column_is_refused_before_evaluation() -> None:
    with pytest.raises(FormulaError, match="não existe"):
        compile_formula("[Inexistente]+1", COLS)
