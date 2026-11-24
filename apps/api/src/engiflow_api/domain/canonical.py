"""Hash canônico do conteúdo lógico de uma tabela (2B.1, §5.1 do planejamento).

Regras:
- Serialização JSON com separadores fixos, sem espaços, chaves ordenadas e UTF-8 sem escape.
- Strings em Unicode NFC. Desconhecido = null; vazio = ""; zero = "0" (são estados distintos).
- Inclui nomes de colunas, valores e a versão do esquema. Não inclui ids, datas, nomes de arquivo.
- Calculado em streaming (linha a linha), sem montar o conteúdo inteiro em memória.

Este hash identifica o CONTEÚDO. O hash de um arquivo exportado (XLSX/CSV) é outra grandeza:
ele depende de metadados do formato e não deve ser usado para comparar conteúdo.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable, Sequence

SCHEMA_VERSION = 1


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class CanonicalHasher:
    """Acumula linhas em streaming e produz o SHA-256 do conteúdo lógico."""

    def __init__(self, columns: Sequence[str]) -> None:
        self._hasher = hashlib.sha256()
        header = {"schema": SCHEMA_VERSION, "columns": [_nfc(c) for c in columns]}
        self._hasher.update((_dump(header) + "\n").encode("utf-8"))
        self.row_count = 0

    def add_row(self, values: Sequence[str | None]) -> None:
        cells: list[str | None] = [None if v is None else _nfc(v) for v in values]
        self._hasher.update((_dump(cells) + "\n").encode("utf-8"))
        self.row_count += 1

    def hexdigest(self) -> str:
        return self._hasher.copy().hexdigest()


def content_sha256(columns: Sequence[str], rows: Iterable[Sequence[str | None]]) -> str:
    hasher = CanonicalHasher(columns)
    for row in rows:
        hasher.add_row(row)
    return hasher.hexdigest()
