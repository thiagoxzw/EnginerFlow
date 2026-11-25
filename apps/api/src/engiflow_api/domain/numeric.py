"""Interpretação numérica com Decimal. Sem ponto flutuante em nenhum cálculo.

Aceita formato brasileiro ("1.234,56") e formato com ponto decimal ("1234.56").
Texto que não é número retorna None: quem chama decide como reportar.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_PLAIN = re.compile(r"^-?\d+(\.\d+)?$")
_BR = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")


def parse_decimal(text: str | None) -> Decimal | None:
    """Converte texto numérico em Decimal. Retorna None se não for um número válido."""
    if text is None:
        return None
    raw = text.strip()
    if raw == "":
        return None
    if "," in raw:
        # Formato brasileiro: ponto é separador de milhar, vírgula é decimal.
        if not _BR.match(raw):
            return None
        normalized = raw.replace(".", "").replace(",", ".")
    else:
        if not _PLAIN.match(raw):
            return None
        normalized = raw
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return value


def format_decimal(value: Decimal) -> str:
    """Texto sem notação científica e sem zeros decimais desnecessários."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text
