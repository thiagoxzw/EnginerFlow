"""Exportação de resultados em CSV e XLSX, com códigos sempre como texto.

- CSV: separador ';' (padrão do Excel em português do Brasil), UTF-8 com BOM para o Excel abrir
  acentos corretamente. Valores que o Excel interpretaria como fórmula recebem apóstrofo.
  Códigos numéricos (ex.: '-0123') não são alterados.
- XLSX: cada célula textual é gravada com tipo string explícito (nunca fórmula) e formato '@'
  (Texto), para que o Excel não converta códigos em número ao abrir ou editar.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

_FORMULA_PREFIXES = ("=", "+", "@", "\t", "\r")
_NUMBERLIKE = re.compile(r"^-\d")


def _csv_cell(value: str) -> str:
    if value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    if value.startswith("-") and not _NUMBERLIKE.match(value):
        return "'" + value
    return value


def to_csv_bytes(headers: Sequence[str], rows: Sequence[Sequence[str | None]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_cell("" if cell is None else str(cell)) for cell in row])
    return buffer.getvalue().encode("utf-8-sig")


@dataclass(frozen=True)
class Sheet:
    title: str
    headers: Sequence[str]
    rows: Sequence[Sequence[str | None]]


def _safe_title(title: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "_", title)[:31] or "Planilha"
    candidate = base
    counter = 2
    while candidate in used:
        suffix = f" ({counter})"
        candidate = base[: 31 - len(suffix)] + suffix
        counter += 1
    used.add(candidate)
    return candidate


def to_xlsx_bytes(sheets: Sequence[Sheet]) -> bytes:
    workbook = Workbook()
    default = workbook.active
    if default is not None:
        workbook.remove(default)
    used: set[str] = set()
    for sheet in sheets:
        worksheet = workbook.create_sheet(title=_safe_title(sheet.title, used))
        all_rows: list[Sequence[str | None]] = [sheet.headers, *sheet.rows]
        for row_index, row in enumerate(all_rows, start=1):
            for column_index, value in enumerate(row, start=1):
                cell = worksheet.cell(row=row_index, column=column_index)
                text = "" if value is None else str(value)
                cell.value = text
                cell.data_type = "s"  # string explícita: nunca fórmula
                cell.number_format = "@"  # formato Texto para o Excel não converter
        for column_index in range(1, len(sheet.headers) + 1):
            worksheet.column_dimensions[get_column_letter(column_index)].width = 18
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
