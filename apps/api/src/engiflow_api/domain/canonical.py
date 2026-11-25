"""Hashes canônicos e determinísticos (2B.2, §5 do planejamento).

Duas grandezas, separadas por finalidade:
- `rows_sha256`: conteúdo lógico das LINHAS de uma versão de dados. Não inclui nomes de colunas,
  para que uma renomeação (metadado) não altere o hash dos dados.
- `metadata_sha256`: colunas, mapeamento e linha de cabeçalho de uma versão de metadados.

Regras de serialização:
- JSON com separadores fixos, sem espaços, chaves ordenadas e UTF-8 sem escape.
- Strings em Unicode NFC. Desconhecido = null; vazio = ""; zero = "0" (estados distintos).
- Calculado em streaming. Não inclui ids, datas, nomes de arquivo nem ordem de inserção.

O hash do ARQUIVO exportado (XLSX/CSV) é outra grandeza e não é usado para comparar conteúdo.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable, Mapping, Sequence

ROWS_SCHEMA = "rows-v1"
METADATA_SCHEMA = "metadata-v1"


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class RowsHasher:
    """Acumula linhas em streaming e produz o SHA-256 do conteúdo das linhas."""

    def __init__(self) -> None:
        self._hasher = hashlib.sha256()
        self._hasher.update((_dump({"schema": ROWS_SCHEMA}) + "\n").encode("utf-8"))
        self.row_count = 0

    def add_row(self, values: Sequence[str | None]) -> None:
        cells: list[str | None] = [None if v is None else _nfc(v) for v in values]
        self._hasher.update((_dump(cells) + "\n").encode("utf-8"))
        self.row_count += 1

    def hexdigest(self) -> str:
        return self._hasher.copy().hexdigest()


def rows_sha256(rows: Iterable[Sequence[str | None]]) -> str:
    hasher = RowsHasher()
    for row in rows:
        hasher.add_row(row)
    return hasher.hexdigest()


def metadata_sha256(
    columns: Sequence[str], mapping: Mapping[str, str], header_row: int | None
) -> str:
    payload = {
        "schema": METADATA_SCHEMA,
        "columns": [_nfc(c) for c in columns],
        "mapping": {_nfc(k): _nfc(v) for k, v in mapping.items()},
        "header_row": header_row,
    }
    return hashlib.sha256(_dump(payload).encode("utf-8")).hexdigest()
