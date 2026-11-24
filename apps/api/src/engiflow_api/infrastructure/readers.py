"""Leitura de CSV e XLSX com proteções (SECURITY_MODEL §5).

- Tipo validado pelo conteúdo (assinatura), não pela extensão.
- Limites de tamanho, linhas e colunas.
- XLSX: verificação de zip bomb antes de abrir a planilha; leitura somente-leitura.
- Todas as células viram texto. Fórmulas não são executadas (leitura do valor em cache).
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time

from openpyxl import load_workbook

from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.tabular import Table, clean_text, detect_header_index, unique_headers

_XLSX_MAGIC = b"PK\x03\x04"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True)
class ImportLimits:
    max_upload_bytes: int = 100 * 1024 * 1024
    max_rows: int = 500_000
    max_columns: int = 200
    max_uncompressed_bytes: int = 500 * 1024 * 1024
    max_zip_entries: int = 2_000
    max_zip_ratio: float = 100.0


def detect_kind(data: bytes) -> str:
    if data.startswith(_XLSX_MAGIC):
        return "xlsx"
    if data.startswith(_XLS_MAGIC):
        raise DomainError("Arquivo .xls (formato antigo) não é suportado. Salve como .xlsx ou CSV.")
    if b"\x00" in data[:4096]:
        raise DomainError("Conteúdo binário não reconhecido. Envie um XLSX ou CSV de texto.")
    return "csv"


def _check_zip(data: bytes, limits: ImportLimits) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise DomainError("Arquivo XLSX inválido ou corrompido.") from exc
    if len(infos) > limits.max_zip_entries:
        raise DomainError("XLSX com número excessivo de partes internas.")
    total = sum(info.file_size for info in infos)
    if total > limits.max_uncompressed_bytes:
        raise DomainError("XLSX descompactado excede o limite permitido.")
    for info in infos:
        if info.compress_size and info.file_size / info.compress_size > limits.max_zip_ratio:
            raise DomainError("XLSX com razão de compressão suspeita (possível zip bomb).")


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError as exc:
        raise DomainError(
            "Não foi possível decodificar o CSV (esperado UTF-8 ou Windows-1252)."
        ) from exc


def _detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def _table_from_raw(
    raw_rows: list[list[str]],
    *,
    sheet: str | None,
    limits: ImportLimits,
    warnings: list[str],
) -> Table:
    if len(raw_rows) > limits.max_rows + 50:
        raise DomainError(f"Arquivo excede o limite de {limits.max_rows} linhas.")
    if not raw_rows:
        raise DomainError("Arquivo sem conteúdo.")
    header_index = detect_header_index(raw_rows)
    header_cells = raw_rows[header_index]
    if len(header_cells) > limits.max_columns:
        raise DomainError(f"Tabela excede o limite de {limits.max_columns} colunas.")
    columns = unique_headers(header_cells)
    width = len(columns)

    body: list[list[str]] = []
    row_numbers: list[int] = []
    for index in range(header_index + 1, len(raw_rows)):
        row = raw_rows[index]
        cleaned = [clean_text(c) for c in (row + [""] * width)[:width]]
        if not any(cleaned):
            continue
        body.append(cleaned)
        row_numbers.append(index + 1)  # número da linha na origem, 1-based
    if len(body) > limits.max_rows:
        raise DomainError(f"Arquivo excede o limite de {limits.max_rows} linhas.")
    return Table(
        columns=columns,
        rows=body,
        row_numbers=row_numbers,
        sheet=sheet,
        warnings=warnings,
    )


def read_csv(data: bytes, limits: ImportLimits) -> Table:
    text = _decode_text(data)
    delimiter = _detect_delimiter(text[:4096])
    raw_rows = [list(r) for r in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return _table_from_raw(raw_rows, sheet=None, limits=limits, warnings=[])


def _cell_to_text(value: object) -> tuple[str, bool]:
    """Converte célula do Excel em texto. Retorna (texto, era_numérica)."""
    if value is None:
        return "", False
    if isinstance(value, bool):
        return ("TRUE" if value else "FALSE"), False
    if isinstance(value, int):
        return str(value), True
    if isinstance(value, float):
        return (str(int(value)) if value.is_integer() else repr(value)), True
    if isinstance(value, datetime | date | time):
        return value.isoformat(), False
    return str(value), False


def list_sheets(data: bytes, limits: ImportLimits) -> list[str]:
    _check_zip(data, limits)
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        return [str(name) for name in workbook.sheetnames]
    finally:
        workbook.close()


def read_xlsx(data: bytes, sheet: str | None, limits: ImportLimits) -> Table:
    _check_zip(data, limits)
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        names = [str(n) for n in workbook.sheetnames]
        if not names:
            raise DomainError("Planilha sem abas.")
        target = sheet if sheet is not None else names[0]
        if target not in names:
            raise DomainError(f"Aba '{target}' não existe. Abas disponíveis: {', '.join(names)}.")
        worksheet = workbook[target]
        raw_rows: list[list[str]] = []
        numeric_cells = 0
        for row in worksheet.iter_rows(values_only=True):
            cells: list[str] = []
            for value in row:
                text, was_numeric = _cell_to_text(value)
                numeric_cells += int(was_numeric)
                cells.append(text)
            raw_rows.append(cells)
            if len(raw_rows) > limits.max_rows + 50:
                raise DomainError(f"Planilha excede o limite de {limits.max_rows} linhas.")
    finally:
        workbook.close()

    warnings: list[str] = []
    if numeric_cells:
        warnings.append(
            f"{numeric_cells} célula(s) numérica(s) foram convertidas em texto. Zeros à esquerda "
            "já perdidos na origem não são recuperáveis: formate as colunas de código como Texto "
            "no Excel antes de exportar."
        )
    return _table_from_raw(raw_rows, sheet=target, limits=limits, warnings=warnings)
