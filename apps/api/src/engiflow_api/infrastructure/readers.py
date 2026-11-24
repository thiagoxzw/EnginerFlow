"""Leitura de CSV e XLSX em streaming, com proteções (SECURITY_MODEL §5).

- Tipo validado pelo conteúdo (assinatura), não pela extensão.
- Limites de linhas e colunas, verificados durante a leitura.
- XLSX: verificação de zip bomb antes de abrir; leitura somente-leitura, linha a linha.
- CSV: leitura linha a linha do arquivo em disco. Nada é carregado inteiro na memória.
- Todas as células viram texto. Fórmulas não são executadas (valor em cache).

Memória: a leitura mantém apenas as primeiras linhas (para achar o cabeçalho) e a linha atual.
O consumidor grava em lotes. O uso real de memória é medido em scripts/bench_data_studio.py.
"""

from __future__ import annotations

import csv
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import load_workbook

from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.tabular import clean_text, detect_header_index, unique_headers

_XLSX_MAGIC = b"PK\x03\x04"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_HEADER_SCAN = 20
_SNIFF_BYTES = 65_536


@dataclass(frozen=True)
class ImportLimits:
    max_upload_bytes: int = 100 * 1024 * 1024
    max_rows: int = 500_000
    max_columns: int = 200
    max_uncompressed_bytes: int = 500 * 1024 * 1024
    max_zip_entries: int = 2_000
    max_zip_ratio: float = 100.0


@dataclass
class TableStream:
    """Cabeçalho já resolvido e linhas em streaming: (número na origem, valores)."""

    columns: list[str]
    sheet: str | None
    rows: Iterator[tuple[int, list[str]]]
    # Preenchido ao final da leitura (avisos dependem do conteúdo lido).
    warnings: list[str] = field(default_factory=list)


def detect_kind_file(path: Path) -> str:
    with path.open("rb") as fh:
        head = fh.read(4096)
    if head.startswith(_XLSX_MAGIC):
        return "xlsx"
    if head.startswith(_XLS_MAGIC):
        raise DomainError("Arquivo .xls (formato antigo) não é suportado. Salve como .xlsx ou CSV.")
    if b"\x00" in head:
        raise DomainError("Conteúdo binário não reconhecido. Envie um XLSX ou CSV de texto.")
    return "csv"


def check_zip_file(path: Path, limits: ImportLimits) -> None:
    """Verifica zip bomb antes de abrir a planilha. Não extrai nada."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise DomainError("Arquivo XLSX inválido ou corrompido.") from exc
    if len(infos) > limits.max_zip_entries:
        raise DomainError("XLSX com número excessivo de partes internas.")
    if sum(info.file_size for info in infos) > limits.max_uncompressed_bytes:
        raise DomainError("XLSX descompactado excede o limite permitido.")
    for info in infos:
        if info.compress_size and info.file_size / info.compress_size > limits.max_zip_ratio:
            raise DomainError("XLSX com razão de compressão suspeita (possível zip bomb).")


def _sniff_text_encoding(path: Path) -> str:
    with path.open("rb") as fh:
        head = fh.read(_SNIFF_BYTES)
    try:
        head.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError as exc:
        # Amostra cortada no meio de um caractere multibyte ainda é UTF-8.
        if exc.reason == "unexpected end of data" and exc.start >= len(head) - 3:
            return "utf-8-sig"
    return "cp1252"


def _sniff_delimiter(path: Path, encoding: str) -> str:
    with path.open("rb") as fh:
        sample = fh.read(4096).decode(encoding, errors="ignore")
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def _build_stream(
    raw: Iterator[tuple[int, list[str]]],
    *,
    sheet: str | None,
    limits: ImportLimits,
    warnings: list[str],
) -> TableStream:
    """Consome só as primeiras linhas para achar o cabeçalho; o resto é streaming."""
    head: list[tuple[int, list[str]]] = []
    for item in raw:
        head.append(item)
        if len(head) >= _HEADER_SCAN:
            break
    if not head:
        raise DomainError("Arquivo sem conteúdo.")
    header_index = detect_header_index([values for _, values in head])
    header_cells = head[header_index][1]
    if len(header_cells) > limits.max_columns:
        raise DomainError(f"Tabela excede o limite de {limits.max_columns} colunas.")
    columns = unique_headers(header_cells)
    width = len(columns)

    def rows() -> Iterator[tuple[int, list[str]]]:
        emitted = 0
        pending = head[header_index + 1 :]
        for number, values in _chain(pending, raw):
            cleaned = [clean_text(c) for c in (values + [""] * width)[:width]]
            if not any(cleaned):
                continue
            emitted += 1
            if emitted > limits.max_rows:
                raise DomainError(f"Arquivo excede o limite de {limits.max_rows} linhas.")
            yield number, cleaned

    return TableStream(columns=columns, sheet=sheet, rows=rows(), warnings=warnings)


def _chain(
    first: list[tuple[int, list[str]]], rest: Iterator[tuple[int, list[str]]]
) -> Iterator[tuple[int, list[str]]]:
    yield from first
    yield from rest


def _decode_guarded(
    lines: Iterator[tuple[int, list[str]]],
) -> Iterator[tuple[int, list[str]]]:
    try:
        yield from lines
    except UnicodeDecodeError as exc:
        raise DomainError(
            "Codificação inconsistente no CSV: o arquivo mistura UTF-8 e outra codificação."
        ) from exc


@contextmanager
def open_csv(path: Path, limits: ImportLimits) -> Iterator[TableStream]:
    encoding = _sniff_text_encoding(path)
    delimiter = _sniff_delimiter(path, encoding)
    with path.open("r", encoding=encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        raw = _decode_guarded((number, row) for number, row in enumerate(reader, start=1))
        yield _build_stream(raw, sheet=None, limits=limits, warnings=[])


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


def list_sheets_file(path: Path, limits: ImportLimits) -> list[str]:
    check_zip_file(path, limits)
    # Abre por handle: o openpyxl exige extensão .xlsx no caminho, e o temporário não tem.
    with path.open("rb") as fh:
        workbook = load_workbook(fh, read_only=True, data_only=True)
        try:
            return [str(name) for name in workbook.sheetnames]
        finally:
            workbook.close()


@contextmanager
def open_xlsx(path: Path, sheet: str | None, limits: ImportLimits) -> Iterator[TableStream]:
    check_zip_file(path, limits)
    with path.open("rb") as fh:
        workbook = load_workbook(fh, read_only=True, data_only=True)
        try:
            names = [str(n) for n in workbook.sheetnames]
            if not names:
                raise DomainError("Planilha sem abas.")
            target = sheet if sheet is not None else names[0]
            if target not in names:
                raise DomainError(
                    f"Aba '{target}' não existe. Abas disponíveis: {', '.join(names)}."
                )
            worksheet = workbook[target]
            warnings: list[str] = []
            numeric = [0]

            def raw() -> Iterator[tuple[int, list[str]]]:
                for number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                    cells: list[str] = []
                    for value in row:
                        text, was_numeric = _cell_to_text(value)
                        numeric[0] += int(was_numeric)
                        cells.append(text)
                    yield number, cells

            stream = _build_stream(raw(), sheet=target, limits=limits, warnings=warnings)
            body = stream.rows

            def rows_then_warn() -> Iterator[tuple[int, list[str]]]:
                yield from body
                if numeric[0]:
                    warnings.append(
                        f"{numeric[0]} célula(s) numérica(s) foram convertidas em texto. Zeros à "
                        "esquerda já perdidos na origem não são recuperáveis: formate as colunas "
                        "de código como Texto no Excel antes de exportar."
                    )

            stream.rows = rows_then_warn()
            yield stream
        finally:
            workbook.close()
