"""Super-PROCV: busca de correspondências exatas entre duas tabelas (2B.3, bloco 1).

Regras:
- Chave é comparada pelo texto canônico (NFC). Zeros à esquerda e especificações são preservados:
  "00123" não casa com "0123". Nenhuma chave é convertida para número.
- Chave desconhecida (None) ou vazia ("") nunca casa: recebe status próprio.
- A tabela de busca (direita) é indexada em memória; o número de chaves distintas é limitado.
- Nenhuma correspondência aproximada entra no resultado aqui; sugestões são outra operação.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from engiflow_api.domain.errors import DomainError

STATUS_FOUND = "encontrado"
STATUS_NOT_FOUND = "não encontrado"
STATUS_MULTIPLE = "múltiplas correspondências"
STATUS_INVALID_KEY = "chave inválida"

DuplicatePolicy = Literal["first", "all", "error"]
UnmatchedPolicy = Literal["keep_empty", "drop"]

MAX_KEYS = 500_000  # teto de chaves distintas indexadas em memória
MAX_RETURN_COLUMNS = 50
MAX_REPORT_ITEMS = 100  # amostra limitada no relatório (contagens são sempre completas)

Index = dict[tuple[str, ...], list[list[str | None]]]


@dataclass(frozen=True)
class LookupPolicy:
    duplicates: DuplicatePolicy = "first"
    unmatched: UnmatchedPolicy = "keep_empty"

    def __post_init__(self) -> None:
        if self.duplicates not in ("first", "all", "error"):
            raise DomainError("Política de duplicatas inválida.")
        if self.unmatched not in ("keep_empty", "drop"):
            raise DomainError("Política de não encontrados inválida.")


@dataclass
class LookupResult:
    rows: list[tuple[int, list[str | None]]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    unmatched_keys: list[str] = field(default_factory=list)
    duplicate_keys: list[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return self.counts.get(status, 0)


def canonical_key(value: str | None) -> str | None:
    """Texto canônico da chave: NFC, sem alterar zeros, espaços das extremidades removidos.

    Retorna None para desconhecido ou vazio (ambos nunca casam).
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFC", value).strip()
    return text or None


def composite_key(values: Sequence[str | None], indexes: Sequence[int]) -> tuple[str, ...] | None:
    """Chave composta canônica. None se qualquer parte for desconhecida ou vazia."""
    parts: list[str] = []
    for index in indexes:
        part = canonical_key(values[index])
        if part is None:
            return None
        parts.append(part)
    return tuple(parts)


def build_index(
    right: Iterable[tuple[int, list[str | None]]],
    right_key: Sequence[int],
    return_index: Sequence[int],
) -> Index:
    """Indexa a tabela de busca: chave -> valores das colunas a retornar (uma lista por linha)."""
    if len(return_index) > MAX_RETURN_COLUMNS:
        raise DomainError(f"No máximo {MAX_RETURN_COLUMNS} colunas de retorno.")
    index: Index = {}
    for _number, values in right:
        key = composite_key(values, right_key)
        if key is None:
            continue
        if key not in index:
            if len(index) >= MAX_KEYS:
                raise DomainError(
                    f"A tabela de busca tem mais de {MAX_KEYS} chaves distintas. "
                    "Reduza a tabela antes de cruzar."
                )
            index[key] = []
        index[key].append([values[i] for i in return_index])
    return index


def lookup(
    left: Iterable[tuple[int, list[str | None]]],
    index: Index,
    left_key: Sequence[int],
    return_width: int,
    policy: LookupPolicy,
    max_rows: int | None = None,
) -> LookupResult:
    """Aplica a busca linha a linha da tabela de consulta (streaming).

    `return_width` é o número de colunas retornadas (usado para preencher vazios).
    """
    result = LookupResult(
        counts={
            STATUS_FOUND: 0,
            STATUS_NOT_FOUND: 0,
            STATUS_MULTIPLE: 0,
            STATUS_INVALID_KEY: 0,
        }
    )
    blanks: list[str | None] = [None] * return_width
    for number, values in left:
        if max_rows is not None and len(result.rows) > max_rows:
            raise DomainError(
                f"O resultado passa de {max_rows} linhas. Reduza as tabelas ou filtre antes."
            )
        key = composite_key(values, left_key)
        if key is None:
            result.counts[STATUS_INVALID_KEY] += 1
            if policy.unmatched == "keep_empty":
                result.rows.append((number, [*values, *blanks, STATUS_INVALID_KEY, "0"]))
            continue

        matches = index.get(key, [])
        if not matches:
            result.counts[STATUS_NOT_FOUND] += 1
            if len(result.unmatched_keys) < MAX_REPORT_ITEMS:
                result.unmatched_keys.append("|".join(key))
            if policy.unmatched == "keep_empty":
                result.rows.append((number, [*values, *blanks, STATUS_NOT_FOUND, "0"]))
            continue

        if len(matches) == 1:
            result.counts[STATUS_FOUND] += 1
            result.rows.append((number, [*values, *matches[0], STATUS_FOUND, "1"]))
            continue

        result.counts[STATUS_MULTIPLE] += 1
        if len(result.duplicate_keys) < MAX_REPORT_ITEMS:
            result.duplicate_keys.append("|".join(key))
        if policy.duplicates == "error":
            raise DomainError(
                "Há chaves com múltiplas correspondências. Escolha outra política de duplicatas "
                "ou revise a tabela de busca."
            )
        if policy.duplicates == "first":
            result.rows.append((number, [*values, *matches[0], STATUS_MULTIPLE, str(len(matches))]))
        else:  # all: uma linha por correspondência
            for match in matches:
                result.rows.append((number, [*values, *match, STATUS_MULTIPLE, str(len(matches))]))
    return result
