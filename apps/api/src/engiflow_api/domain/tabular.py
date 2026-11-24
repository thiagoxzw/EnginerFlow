"""Regras tabulares puras (sem framework, sem banco).

Decisões (ADR-0008, ADR-0006, PRD RF-04 a RF-07):
- Códigos são sempre texto. Nunca convertidos para número, zeros à esquerda são preservados.
- Comparação de códigos usa chave sem diferença de caixa nem espaços nas bordas.
  Zeros são preservados na chave.
- Códigos que diferem só por zeros à esquerda são *sugestão* de equivalência, nunca fusão.
- Descrições semelhantes geram sugestão com score e evidência. Sem equivalência automática.
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
_TOKEN = re.compile(r"[a-z0-9]+")
# Tokens presentes em muitas descrições geram pares demais. Acima deste número de ocorrências,
# o token não é usado para gerar candidatos (ver limitação em FASE_2_STATUS.md).
MAX_TOKEN_DOCUMENT_FREQUENCY = 500


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


def zero_group(key: str) -> str:
    """Grupo de códigos que diferem só por zeros à esquerda. '000' e '0' pertencem ao grupo '0'."""
    stripped = key.lstrip("0")
    return stripped if stripped else "0"


def normalize_description(value: str) -> str:
    """Descrição normalizada: sem acentos, caixa baixa, pontuação removida, espaços colapsados."""
    decomposed = unicodedata.normalize("NFKD", clean_text(value))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(_TOKEN.findall(stripped.casefold()))


def description_tokens(value: str) -> list[str]:
    return normalize_description(value).split()


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
    """Todos os pares de chaves distintas que pertencem ao mesmo grupo de zeros."""
    by_group: dict[str, set[str]] = {}
    for raw in codes:
        if not clean_text(raw):
            continue
        key = code_key(raw)
        by_group.setdefault(zero_group(key), set()).add(key)
    out: list[LeadingZeroSuspicion] = []
    for keys in by_group.values():
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
    reason: str


def _reason(norm_a: str, norm_b: str) -> str:
    if norm_a == norm_b:
        return "descrição idêntica"
    if sorted(norm_a.split()) == sorted(norm_b.split()):
        return "mesmos termos em outra ordem"
    return "texto semelhante"


def similar_descriptions(
    items: Sequence[tuple[int, str]],
    threshold: float = 0.85,
    max_items: int = 5000,
) -> list[SimilarPair]:
    """Pares de descrições semelhantes, com score (0 a 1) e evidência.

    - Candidatos vêm de um índice invertido por token: descrições que compartilham um token
      (independentemente da ordem) são comparadas. Tokens presentes em mais de
      MAX_TOKEN_DOCUMENT_FREQUENCY descrições não geram candidatos.
    - Score = maior entre a razão de similaridade do texto na ordem original e a razão com os
      termos ordenados. Assim 'M8 PARAFUSO' e 'PARAFUSO M8' têm score 1.0.
    - Sem equivalência automática: o resultado é sugestão para revisão humana.
    """
    if len(items) > max_items:
        raise DomainError(
            f"Comparação aproximada limitada a {max_items} descrições. "
            "Filtre o conjunto antes de comparar."
        )
    prepared: list[tuple[int, str, str, str, frozenset[str]]] = []
    for row, value in items:
        cleaned = clean_text(value)
        if not cleaned:
            continue
        norm = normalize_description(cleaned)
        tokens = norm.split()
        prepared.append((row, cleaned, norm, " ".join(sorted(tokens)), frozenset(tokens)))

    index: dict[str, list[int]] = {}
    for position, entry in enumerate(prepared):
        for token in entry[4]:
            index.setdefault(token, []).append(position)

    candidate_pairs: set[tuple[int, int]] = set()
    for members in index.values():
        if len(members) > MAX_TOKEN_DOCUMENT_FREQUENCY:
            continue
        for a_pos, i in enumerate(members):
            for j in members[a_pos + 1 :]:
                candidate_pairs.add((i, j) if i < j else (j, i))

    pairs: list[SimilarPair] = []
    for i, j in candidate_pairs:
        row_i, value_i, norm_i, sorted_i, tokens_i = prepared[i]
        row_j, value_j, norm_j, sorted_j, tokens_j = prepared[j]
        if norm_i == norm_j:
            score = 1.0
        else:
            score = max(
                SequenceMatcher(None, norm_i, norm_j).ratio(),
                SequenceMatcher(None, sorted_i, sorted_j).ratio(),
            )
        if score < threshold:
            continue
        pairs.append(
            SimilarPair(
                row_a=row_i,
                row_b=row_j,
                value_a=value_i,
                value_b=value_j,
                score=round(score, 4),
                shared_tokens=sorted(tokens_i & tokens_j),
                reason=_reason(norm_i, norm_j),
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
    """Compara dois conjuntos de códigos pela chave de comparação (sem fusão automática).

    Candidatos por zeros à esquerda são calculados contra TODAS as chaves do outro lado
    (inclusive as que existem nos dois lados), para não perder nenhuma sugestão.
    """
    left_keys = {code_key(c) for c in left if clean_text(c)}
    right_keys = {code_key(c) for c in right if clean_text(c)}
    right_by_group: dict[str, list[str]] = {}
    for key in right_keys:
        right_by_group.setdefault(zero_group(key), []).append(key)

    candidates: list[tuple[str, str]] = []
    for key in sorted(left_keys):
        for other in sorted(right_by_group.get(zero_group(key), [])):
            if other != key:
                candidates.append((key, other))

    return CodeComparison(
        only_left=sorted(left_keys - right_keys),
        only_right=sorted(right_keys - left_keys),
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
