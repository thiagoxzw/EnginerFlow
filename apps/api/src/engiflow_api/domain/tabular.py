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
# Designações letra+número (M8 -> m8), números com decimal e palavras.
# Dimensão "8x20" vira 8, x, 20; "10,5mm" vira 10.5, mm.
_TOKEN = re.compile(r"[a-z]+\d+(?:\.\d+)?|\d+(?:\.\d+)?|[a-z]+")
_DIMENSION_X = re.compile(r"(?<=\d)x(?=\d)")
_DECIMAL_COMMA = re.compile(r"(\d),(\d)")
# Símbolos técnicos preservados como palavras (não podem ser descartados na comparação).
_SYMBOLS = (
    ("Ø", " diam "),
    ("ø", " diam "),
    ("⌀", " diam "),
    ("±", " tol "),
    ("°", " graus "),
    ("×", " x "),
    ("%", " pct "),
)
# Palavras que fazem parte da especificação (unidades e símbolos).
SPEC_WORDS = frozenset(
    {
        "diam",
        "tol",
        "graus",
        "pct",
        "x",
        "mm",
        "cm",
        "m",
        "kg",
        "g",
        "ml",
        "l",
        "kw",
        "bar",
        "v",
        "a",
    }
)
MAX_CANDIDATE_PAIRS = 300_000
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
    """Descrição normalizada para comparação.

    Sem acentos e caixa baixa; símbolos técnicos viram palavras (Ø -> diam, ± -> tol, ° -> graus,
    × -> x, % -> pct); vírgula decimal vira ponto. Assim '10,5' != '105', 'Ø10' != '10' e
    '±0,1' != '0,1'. Pontuação comum é descartada.
    """
    decomposed = unicodedata.normalize("NFKD", clean_text(value))
    text = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    for symbol, word in _SYMBOLS:
        text = text.replace(symbol.casefold(), word)
    text = _DECIMAL_COMMA.sub(r"\1.\2", text)
    text = _DIMENSION_X.sub(" x ", text)
    return " ".join(_TOKEN.findall(text))


def spec_signature(tokens: Sequence[str]) -> tuple[str, ...]:
    """Especificação técnica: números e unidades/símbolos, em ordem canônica."""
    return tuple(sorted(t for t in tokens if any(ch.isdigit() for ch in t) or t in SPEC_WORDS))


def description_tokens(value: str) -> list[str]:
    return normalize_description(value).split()


def detect_header_index(rows: Sequence[Sequence[str]], max_scan: int = 20) -> int:
    """Escolhe a linha de cabeçalho entre as primeiras linhas.

    Critério: a PRIMEIRA linha com >= 2 células preenchidas, largura compatível com a linha mais
    larga da amostra, sem números puros e com nomes únicos. Sem candidato, usa a linha mais
    textual (desempate pela largura, depois pela primeira ocorrência).
    """
    candidates: list[tuple[int, list[str]]] = []
    for idx, row in enumerate(rows[:max_scan]):
        filled = [clean_text(c) for c in row if clean_text(c)]
        if len(filled) >= 2:
            candidates.append((idx, filled))
    if not candidates:
        return 0
    widest = max(len(filled) for _, filled in candidates)
    for idx, filled in candidates:
        if len(filled) < max(2, round(0.5 * widest)):
            continue
        if any(_NUMERIC.match(c) for c in filled):
            continue
        if len({c.casefold() for c in filled}) != len(filled):
            continue
        return idx
    best = max(
        candidates,
        key=lambda item: (sum(1 for c in item[1] if not _NUMERIC.match(c)), len(item[1]), -item[0]),
    )
    return best[0]


def unique_headers(raw: Iterable[str]) -> list[str]:
    """Nomes não vazios e únicos, sem diferença de caixa.

    Vazio vira 'Coluna N'. Repetido ganha sufixo '(n)' com o menor n que não colide com nenhum
    nome já usado, inclusive nomes originais como 'A (2)'.
    """
    used: set[str] = set()
    out: list[str] = []
    for position, name in enumerate(raw, start=1):
        base = clean_text(name) or f"Coluna {position}"
        candidate = base
        counter = 2
        while candidate.casefold() in used:
            candidate = f"{base} ({counter})"
            counter += 1
        used.add(candidate.casefold())
        out.append(candidate)
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


def _check_candidate_cap(count: int) -> None:
    """Limita a memória: candidatos além de MAX_CANDIDATE_PAIRS são recusados."""
    if count > MAX_CANDIDATE_PAIRS:
        raise DomainError(
            f"Muitos candidatos (mais de {MAX_CANDIDATE_PAIRS}). "
            "Filtre o conjunto antes de comparar."
        )


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
                _check_candidate_cap(len(out))
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
    spec_match: bool


def _reason(norm_a: str, norm_b: str, spec_match: bool) -> str:
    if not spec_match:
        return "especificações diferentes: não considerar equivalente"
    if norm_a == norm_b:
        return "descrição idêntica"
    if sorted(norm_a.split()) == sorted(norm_b.split()):
        return "mesmos termos em outra ordem"
    return "texto semelhante"


def _add_group_pairs(members: list[int], pairs: set[tuple[int, int]]) -> None:
    """Acrescenta pares do grupo. Para ao atingir MAX_CANDIDATE_PAIRS (memória limitada)."""
    for a_pos, i in enumerate(members):
        for j in members[a_pos + 1 :]:
            pairs.add((i, j) if i < j else (j, i))
            if len(pairs) > MAX_CANDIDATE_PAIRS:
                raise DomainError(
                    f"Muitos candidatos de comparação (mais de {MAX_CANDIDATE_PAIRS}). "
                    "Filtre o conjunto antes de comparar."
                )


def similar_descriptions(
    items: Sequence[tuple[int, str]],
    threshold: float = 0.85,
    max_items: int = 5000,
) -> list[SimilarPair]:
    """Pares de descrições semelhantes, com score (0 a 1), evidência e flag de especificação.

    Candidatos:
    1. Descrições idênticas e descrições com os mesmos termos (independe da frequência de tokens).
    2. Índice invertido por token. Tokens em mais de MAX_TOKEN_DOCUMENT_FREQUENCY descrições são
       ignorados para candidatos (limitação documentada).
    Score = maior entre a similaridade do texto e a dos termos ordenados.
    Pares com especificações técnicas diferentes (números, unidades, símbolos) aparecem com
    spec_match=False e nunca são tratados como equivalentes.
    """
    if len(items) > max_items:
        raise DomainError(
            f"Comparação aproximada limitada a {max_items} descrições. "
            "Filtre o conjunto antes de comparar."
        )
    prepared: list[tuple[int, str, str, str, frozenset[str], tuple[str, ...]]] = []
    for row, value in items:
        cleaned = clean_text(value)
        if not cleaned:
            continue
        norm = normalize_description(cleaned)
        tokens = norm.split()
        prepared.append(
            (
                row,
                cleaned,
                norm,
                " ".join(sorted(tokens)),
                frozenset(tokens),
                spec_signature(tokens),
            )
        )

    candidate_pairs: set[tuple[int, int]] = set()
    by_norm: dict[str, list[int]] = {}
    by_sorted: dict[str, list[int]] = {}
    for position, entry in enumerate(prepared):
        by_norm.setdefault(entry[2], []).append(position)
        by_sorted.setdefault(entry[3], []).append(position)
    for groups in (by_norm, by_sorted):
        for members in groups.values():
            if len(members) > 1:
                _add_group_pairs(members, candidate_pairs)

    index: dict[str, list[int]] = {}
    for position, entry in enumerate(prepared):
        for token in entry[4]:
            index.setdefault(token, []).append(position)
    for members in index.values():
        if len(members) <= MAX_TOKEN_DOCUMENT_FREQUENCY:
            _add_group_pairs(members, candidate_pairs)

    if len(candidate_pairs) > MAX_CANDIDATE_PAIRS:
        raise DomainError(
            f"Muitos candidatos de comparação ({len(candidate_pairs)}). "
            "Filtre o conjunto antes de comparar."
        )

    pairs: list[SimilarPair] = []
    for i, j in candidate_pairs:
        row_i, value_i, norm_i, sorted_i, tokens_i, spec_i = prepared[i]
        row_j, value_j, norm_j, sorted_j, tokens_j, spec_j = prepared[j]
        spec_match = spec_i == spec_j
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
                reason=_reason(norm_i, norm_j, spec_match),
                spec_match=spec_match,
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
                _check_candidate_cap(len(candidates))

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
