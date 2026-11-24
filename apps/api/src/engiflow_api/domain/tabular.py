"""Regras tabulares puras (sem framework, sem banco).

Decisões (ADR-0008, ADR-0006, PRD RF-04 a RF-07):
- Códigos são sempre texto. Nunca convertidos para número, zeros à esquerda são preservados.
- Comparação de códigos usa chave sem diferença de caixa nem espaços nas bordas.
  Zeros são preservados.
- Zeros à esquerda diferentes são apenas *sugestão* de equivalência, nunca fusão automática.
- Descrições semelhantes geram sugestão com score e evidências. Sem equivalência automática.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from engiflow_api.domain.errors import DomainError

CANONICAL_FIELDS: tuple[str, ...] = ("code", "description", "unit", "quantity", "category")

_WS = re.compile(r"\s+")
_NUMERIC = re.compile(r"^[+-]?\d+([.,]\d+)?$")
_BLOCK_PREFIX = 3


@dataclass(frozen=True)
class Table:
    """Tabela lida de um arquivo. Todas as células são texto."""

    columns: list[str]
    rows: list[list[str]]
    row_numbers: list[int]
    sheet: str | None = None
    warnings: list[str] = field(default_factory=list)


def clean_text(value: str) -> str:
    """Remove espaços das bordas e normaliza espaços internos e espaço não separável."""
    return _WS.sub(" ", value.replace(" ", " ")).strip()


def normalize_code(value: str) -> str:
    """Código como texto limpo. Preserva zeros à esquerda e a caixa original."""
    return clean_text(value)


def code_key(value: str) -> str:
    """Chave de comparação de códigos: texto limpo, sem diferença de caixa, zeros preservados."""
    return normalize_code(value).upper()


def normalize_description(value: str) -> str:
    """Descrição normalizada: sem acentos, caixa baixa, espaços colapsados."""
    decomposed = unicodedata.normalize("NFKD", clean_text(value))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def detect_header_index(rows: Sequence[Sequence[str]], max_scan: int = 20) -> int:
    """Escolhe a linha de cabeçalho entre as primeiras linhas.

    Prefere linhas com muitas células preenchidas e maioria de textos (não números).
    Sem candidato claro, usa a primeira linha.
    """
    best_idx = 0
    best_score = -1
    for idx, row in enumerate(rows[:max_scan]):
        filled = [clean_text(c) for c in row if clean_text(c)]
        if len(filled) < 2:
            continue
        texts = [c for c in filled if not _NUMERIC.match(c)]
        if len(texts) / len(filled) < 0.6:
            continue
        score = len(texts) * 2 + len(filled)
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx


def unique_headers(raw: Iterable[str]) -> list[str]:
    """Nomes de coluna não vazios e únicos. Vazios viram 'Coluna N'; repetidos ganham sufixo."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for position, name in enumerate(raw, start=1):
        base = clean_text(name) or f"Coluna {position}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        out.append(base if count == 1 else f"{base} ({count})")
    return out


@dataclass(frozen=True)
class DuplicateGroup:
    key: str
    row_numbers: list[int]
    values: list[str]


def exact_code_duplicates(items: Sequence[tuple[int, str]]) -> list[DuplicateGroup]:
    """Grupos de códigos repetidos (mesma chave de comparação)."""
    groups: dict[str, list[tuple[int, str]]] = {}
    for row_number, raw in items:
        if not clean_text(raw):
            continue
        groups.setdefault(code_key(raw), []).append((row_number, normalize_code(raw)))
    return [
        DuplicateGroup(key=key, row_numbers=[r for r, _ in members], values=[v for _, v in members])
        for key, members in groups.items()
        if len(members) > 1
    ]


@dataclass(frozen=True)
class LeadingZeroSuspicion:
    """Dois códigos diferentes que só diferem por zeros à esquerda. Exige revisão humana."""

    key_a: str
    key_b: str


def leading_zero_suspicions(codes: Iterable[str]) -> list[LeadingZeroSuspicion]:
    by_stripped: dict[str, set[str]] = {}
    for raw in codes:
        if not clean_text(raw):
            continue
        key = code_key(raw)
        stripped = key.lstrip("0")
        if stripped:
            by_stripped.setdefault(stripped, set()).add(key)
    out: list[LeadingZeroSuspicion] = []
    for keys in by_stripped.values():
        ordered = sorted(keys)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                out.append(LeadingZeroSuspicion(key_a=a, key_b=b))
    return out


@dataclass(frozen=True)
class SimilarPair:
    row_a: int
    row_b: int
    value_a: str
    value_b: str
    score: float
    shared_tokens: list[str]


def similar_descriptions(
    items: Sequence[tuple[int, str]],
    threshold: float = 0.85,
    max_items: int = 5000,
) -> list[SimilarPair]:
    """Pares de descrições semelhantes, com score (0 a 1) e tokens em comum como evidência.

    Usa blocagem pelos primeiros caracteres para não comparar todos contra todos. Isso perde
    pares cujos prefixos diferem (ex.: 'M8 PARAFUSO' x 'PARAFUSO M8'); a limitação está documentada.
    """
    if len(items) > max_items:
        raise DomainError(
            f"Comparação aproximada limitada a {max_items} descrições. "
            "Filtre o conjunto antes de comparar."
        )
    prepared = [
        (row, clean_text(value), normalize_description(value))
        for row, value in items
        if clean_text(value)
    ]
    blocks: dict[str, list[int]] = {}
    for index, (_, _, norm) in enumerate(prepared):
        blocks.setdefault(norm[:_BLOCK_PREFIX], []).append(index)

    pairs: list[SimilarPair] = []
    for members in blocks.values():
        for a_pos, i in enumerate(members):
            row_i, value_i, norm_i = prepared[i]
            tokens_i = set(norm_i.split())
            for j in members[a_pos + 1 :]:
                row_j, value_j, norm_j = prepared[j]
                score = 1.0 if norm_i == norm_j else SequenceMatcher(None, norm_i, norm_j).ratio()
                if score < threshold:
                    continue
                shared = sorted(tokens_i & set(norm_j.split()))
                pairs.append(
                    SimilarPair(
                        row_a=row_i,
                        row_b=row_j,
                        value_a=value_i,
                        value_b=value_j,
                        score=round(score, 4),
                        shared_tokens=shared,
                    )
                )
    pairs.sort(key=lambda p: (-p.score, p.row_a, p.row_b))
    return pairs


@dataclass(frozen=True)
class CodeComparison:
    only_left: list[str]
    only_right: list[str]
    in_both: list[str]
    leading_zero_candidates: list[tuple[str, str]]


def compare_codes(left: Iterable[str], right: Iterable[str]) -> CodeComparison:
    """Compara dois conjuntos de códigos pela chave de comparação (sem fusão automática)."""
    left_keys = {code_key(c) for c in left if clean_text(c)}
    right_keys = {code_key(c) for c in right if clean_text(c)}
    only_left = sorted(left_keys - right_keys)
    only_right = sorted(right_keys - left_keys)
    right_by_stripped: dict[str, str] = {}
    for key in only_right:
        stripped = key.lstrip("0")
        if stripped:
            right_by_stripped.setdefault(stripped, key)
    candidates: list[tuple[str, str]] = []
    for key in only_left:
        stripped = key.lstrip("0")
        if stripped and stripped in right_by_stripped:
            candidates.append((key, right_by_stripped[stripped]))
    return CodeComparison(
        only_left=only_left,
        only_right=only_right,
        in_both=sorted(left_keys & right_keys),
        leading_zero_candidates=candidates,
    )


def validate_mapping(mapping: dict[str, str], columns: Sequence[str]) -> dict[str, str]:
    """Valida mapeamento campo canônico -> coluna. Retorna o mapeamento limpo."""
    unknown_fields = sorted(set(mapping) - set(CANONICAL_FIELDS))
    if unknown_fields:
        raise DomainError(f"Campos desconhecidos no mapeamento: {', '.join(unknown_fields)}.")
    missing_columns = sorted({c for c in mapping.values() if c not in columns})
    if missing_columns:
        raise DomainError(f"Colunas inexistentes na tabela: {', '.join(missing_columns)}.")
    return dict(mapping)
