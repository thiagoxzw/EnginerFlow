"""Comparação de linhas por chave (2B.3). Pura, em memória sobre a tabela de busca.

Classificação por chave composta canônica (ver `lookup.composite_key`):
- adicionado: chave só na tabela de busca;
- removido: chave só na tabela de origem (esquerda);
- alterado: chave nas duas, com ao menos uma coluna compartilhada diferente;
- idêntico: chave nas duas, sem diferença nas colunas compartilhadas.

Regras:
- Chave com vazio ou desconhecido não casa; é contada como inválida em cada lado.
- Chave repetida na tabela de busca: compara-se com a primeira ocorrência e o caso é reportado.
- Igualdade: texto canônico (espaços das extremidades removidos, zeros preservados);
  se ambos forem números, comparação decimal (ex.: "1,50" = "1.5").
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from engiflow_api.domain.lookup import canonical_key, composite_key
from engiflow_api.domain.numeric import parse_decimal

TYPE_ADDED = "adicionado"
TYPE_REMOVED = "removido"
TYPE_CHANGED = "alterado"
TYPE_IDENTICAL = "idêntico"
WHOLE_ROW = "(linha)"

MAX_SAMPLE = 500


@dataclass
class ComparisonResult:
    counts: dict[str, int]
    columns: list[str]
    rows: list[list[str | None]]
    sample: list[list[str | None]] = field(default_factory=list)


def values_equal(a: str | None, b: str | None) -> bool:
    """Igualdade de células: decimal quando ambas são números, texto canônico caso contrário."""
    text_a = canonical_key(a) or ""
    text_b = canonical_key(b) or ""
    number_a: Decimal | None = parse_decimal(text_a) if text_a else None
    number_b: Decimal | None = parse_decimal(text_b) if text_b else None
    if number_a is not None and number_b is not None:
        return number_a == number_b
    return text_a == text_b


def _key_text(key: tuple[str, ...]) -> str:
    return " + ".join(key)


def compare(
    left_rows: Iterable[Sequence[str | None]],
    right_rows: Iterable[Sequence[str | None]],
    left_key: Sequence[int],
    right_key: Sequence[int],
    shared: Sequence[tuple[int, int, str]],
    *,
    max_rows: int = 500_000,
) -> ComparisonResult:
    """Compara as duas tabelas.

    `shared` são triplas (índice esquerdo, índice direito, nome) das colunas a comparar.
    """
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
            emit([TYPE_REMOVED, _key_text(key), WHOLE_ROW, "", ""])
            continue
        seen.add(key)
        differences = [
            (name, values[i], match[j])
            for i, j, name in shared
            if not values_equal(values[i], match[j])
        ]
        if not differences:
            counts[TYPE_IDENTICAL] += 1
            continue
        counts[TYPE_CHANGED] += 1
        for name, before, after in differences:
            emit([TYPE_CHANGED, _key_text(key), name, before or "", after or ""])

    for key in right_index:
        if key not in seen:
            counts[TYPE_ADDED] += 1
            emit([TYPE_ADDED, _key_text(key), WHOLE_ROW, "", ""])

    counts["chaves_invalidas_esquerda"] = invalid["esquerda"]
    counts["chaves_invalidas_direita"] = invalid["direita"]
    return ComparisonResult(
        counts=counts,
        columns=["tipo", "chave", "coluna", "antes", "depois"],
        rows=rows,
        sample=rows[:MAX_SAMPLE],
    )
