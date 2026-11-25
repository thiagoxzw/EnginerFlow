"""Comparação de linhas por chave (2B.3). Pura, em memória sobre a tabela de busca.

Classificação por chave composta canônica (ver `lookup.composite_key`):
- adicionado: chave só na tabela de busca;
- removido: chave só na tabela de origem (esquerda);
- alterado: chave nas duas, com ao menos uma coluna comparada diferente;
- idêntico: chave nas duas, sem diferença nas colunas comparadas.

Chaves: texto canônico (NFC, espaços das extremidades removidos). Zeros, maiúsculas e
pontuação são preservados. Nunca há equivalência numérica em chave.

Modos de comparação de VALORES (escolhidos por coluna; padrão `exato`):
- `exato`: igualdade literal. Preserva zeros, caixa, espaços, símbolos e pontuação.
- `normalizado`: NFC, espaços repetidos colapsados, sem diferença de caixa e sem acentos.
- `numerico`: se ambos forem números, compara Decimal ("1,50" = "1.5", "007" = "7").
  Se algum lado não for número, compara como texto exato.
- `descricao_tecnica`: NFC, espaços repetidos colapsados, sem diferença de caixa. Mantém acentos,
  pontuação, separadores e dimensões ("M16X1,5" ≠ "M16X2").

Em todos os modos: desconhecido (None) ≠ vazio ("") ≠ zero ("0").
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from engiflow_api.domain.lookup import composite_key
from engiflow_api.domain.numeric import parse_decimal

TYPE_ADDED = "adicionado"
TYPE_REMOVED = "removido"
TYPE_CHANGED = "alterado"
TYPE_IDENTICAL = "idêntico"
WHOLE_ROW = "(linha)"

MODE_EXACT = "exato"
MODE_NORMALIZED = "normalizado"
MODE_NUMERIC = "numerico"
MODE_TECHNICAL = "descricao_tecnica"
MODES = (MODE_EXACT, MODE_NORMALIZED, MODE_NUMERIC, MODE_TECHNICAL)
MODE_LABELS = {
    MODE_EXACT: "Texto exato",
    MODE_NORMALIZED: "Texto normalizado (caixa, acentos e espaços)",
    MODE_NUMERIC: "Numérico (decimal)",
    MODE_TECHNICAL: "Descrição técnica (caixa e espaços; mantém símbolos)",
}

MAX_SAMPLE = 500


@dataclass
class ComparisonResult:
    counts: dict[str, int]
    columns: list[str]
    rows: list[list[str | None]]
    sample: list[list[str | None]] = field(default_factory=list)


def _collapse(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def values_equal(a: str | None, b: str | None, mode: str = MODE_EXACT) -> bool:
    """Igualdade de valores segundo o modo. Desconhecido (None) só é igual a desconhecido."""
    if mode not in MODES:
        raise ValueError(f"Modo de comparação desconhecido: '{mode}'.")
    if a is None or b is None:
        return a is None and b is None
    if mode == MODE_EXACT:
        return a == b
    if mode == MODE_NORMALIZED:
        return _strip_accents(_collapse(a)) == _strip_accents(_collapse(b))
    if mode == MODE_TECHNICAL:
        return _collapse(a) == _collapse(b)
    number_a = parse_decimal(a)
    number_b = parse_decimal(b)
    if number_a is not None and number_b is not None:
        return number_a == number_b
    return a == b


def _key_text(key: tuple[str, ...]) -> str:
    return " + ".join(key)


def compare(
    left_rows: Iterable[Sequence[str | None]],
    right_rows: Iterable[Sequence[str | None]],
    left_key: Sequence[int],
    right_key: Sequence[int],
    shared: Sequence[tuple[int, int, str]],
    *,
    modes: Mapping[str, str] | None = None,
    max_rows: int = 500_000,
) -> ComparisonResult:
    """Compara as duas tabelas.

    `shared` são triplas (índice esquerdo, índice direito, nome) das colunas a comparar.
    `modes` associa o nome de cada coluna a um modo; colunas ausentes usam `exato`.
    """
    column_modes = dict(modes or {})
    for name in column_modes:
        if column_modes[name] not in MODES:
            raise ValueError(f"Modo de comparação desconhecido para '{name}'.")
    right_index: dict[tuple[str, ...], Sequence[str | None]] = {}
    right_counts: dict[tuple[str, ...], int] = {}
    invalid = {"esquerda": 0, "direita": 0}
    for values in right_rows:
        key = composite_key(values, right_key)
        if key is None:
            invalid["direita"] += 1
            continue
        right_counts[key] = right_counts.get(key, 0) + 1
        right_index.setdefault(key, values)

    counts: dict[str, int] = {
        TYPE_ADDED: 0,
        TYPE_REMOVED: 0,
        TYPE_CHANGED: 0,
        TYPE_IDENTICAL: 0,
        "chaves_duplicadas_busca": sum(1 for n in right_counts.values() if n > 1),
    }
    rows: list[list[str | None]] = []
    seen: set[tuple[str, ...]] = set()

    def emit(row: list[str | None]) -> None:
        if len(rows) >= max_rows:
            raise ValueError(
                f"A comparação passa de {max_rows} linhas de diferença. Filtre antes de comparar."
            )
        rows.append(row)

    for values in left_rows:
        key = composite_key(values, left_key)
        if key is None:
            invalid["esquerda"] += 1
            continue
        match = right_index.get(key)
        if match is None:
            counts[TYPE_REMOVED] += 1
            emit([TYPE_REMOVED, _key_text(key), WHOLE_ROW, None, None])
            continue
        seen.add(key)
        differences = [
            (name, values[i], match[j])
            for i, j, name in shared
            if not values_equal(values[i], match[j], column_modes.get(name, MODE_EXACT))
        ]
        if not differences:
            counts[TYPE_IDENTICAL] += 1
            continue
        counts[TYPE_CHANGED] += 1
        for name, before, after in differences:
            emit([TYPE_CHANGED, _key_text(key), name, before, after])

    for key in right_index:
        if key not in seen:
            counts[TYPE_ADDED] += 1
            emit([TYPE_ADDED, _key_text(key), WHOLE_ROW, None, None])

    counts["chaves_invalidas_esquerda"] = invalid["esquerda"]
    counts["chaves_invalidas_direita"] = invalid["direita"]
    return ComparisonResult(
        counts=counts,
        columns=["tipo", "chave", "coluna", "antes", "depois"],
        rows=rows,
        sample=rows[:MAX_SAMPLE],
    )
