"""Inspeção de arquivo antes da importação: abas, cabeçalho detectado e prévia. Nada é gravado."""

from __future__ import annotations

import io
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import Workbook

from engiflow_api.core.config import Settings


def _xlsx(sheets: dict[str, list[list[Any]]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active) if wb.active is not None else None
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _count_datasets(client: TestClient) -> int:
    body: list[dict[str, Any]] = client.get("/api/v1/datasets").json()
    return len(body)


def test_csv_inspection_reports_header_and_preview_without_importing(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    data = "SYN-Código;SYN-Qtd\n00123;1\n0123;2\n".encode()
    before = _count_datasets(logged_client)
    resp = logged_client.post(
        "/api/v1/datasets/inspect", files={"file": ("SYN-x.csv", data, "text/csv")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "csv"
    assert body["sheets"] == []
    assert body["header_row"] == 1
    assert body["columns"] == ["SYN-Código", "SYN-Qtd"]
    assert body["preview"][1]["values"][0] == "00123"  # zeros preservados na prévia
    assert _count_datasets(logged_client) == before  # nada importado


def test_xlsx_inspection_lists_sheets_and_skips_title_rows(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    data = _xlsx(
        {
            "Materiais": [
                ["Título do relatório"],
                [],
                ["Código", "Descrição"],
                ["000123", "Parafuso"],
            ],
            "Kits": [["Kit", "Componente"], ["K1", "000123"]],
        }
    )
    resp = logged_client.post(
        "/api/v1/datasets/inspect", files={"file": ("SYN-x.xlsx", data, "application/octet-stream")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "xlsx"
    assert body["sheets"] == ["Materiais", "Kits"]
    assert body["sheet"] == "Materiais"
    assert body["header_row"] == 3
    assert body["columns"] == ["Código", "Descrição"]


def test_selecting_another_sheet_changes_the_preview(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    data = _xlsx(
        {
            "Materiais": [["Código", "Descrição"], ["000123", "Parafuso"]],
            "Kits": [["Kit", "Componente"], ["K1", "000123"]],
        }
    )
    resp = logged_client.post(
        "/api/v1/datasets/inspect",
        files={"file": ("SYN-x.xlsx", data, "application/octet-stream")},
        data={"sheet": "Kits"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sheet"] == "Kits"
    assert resp.json()["columns"] == ["Kit", "Componente"]


def test_unknown_sheet_and_empty_file_are_clear_errors(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    data = _xlsx({"Materiais": [["Código"], ["1"]]})
    bad_sheet = logged_client.post(
        "/api/v1/datasets/inspect",
        files={"file": ("SYN-x.xlsx", data, "application/octet-stream")},
        data={"sheet": "Inexistente"},
    )
    assert bad_sheet.status_code == 422
    assert "não existe" in bad_sheet.text

    empty = logged_client.post(
        "/api/v1/datasets/inspect", files={"file": ("SYN-vazio.csv", b"", "text/csv")}
    )
    assert empty.status_code == 422
    assert "vazio" in empty.text
