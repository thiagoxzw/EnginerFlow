"""Data Studio: leitura CSV/XLSX, mapeamento, duplicatas e comparação.

Todas as fixtures são SINTÉTICAS (prefixo SYN-), geradas em código. Nenhum dado real.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from engiflow_api.application.data_studio import import_file
from engiflow_api.core.config import Settings
from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.tabular import (
    code_key,
    compare_codes,
    detect_header_index,
    exact_code_duplicates,
    leading_zero_suspicions,
    normalize_description,
    similar_descriptions,
    unique_headers,
    validate_mapping,
)
from engiflow_api.infrastructure.models import AuditLog
from engiflow_api.infrastructure.readers import ImportLimits, detect_kind, read_csv, read_xlsx

# ---------- fixtures sintéticas ----------

CSV_CP1252 = (
    "SYN-Código;SYN-Descrição;Unidade\n"
    "00123;Parafuso M8 sextavado;UN\n"
    "0123;Parafuso M8 sextavado;UN\n"
    "00123;Porca M8;UN\n"
    "AB1;Arruela lisa 8 mm – ação;UN\n"
    "ab1 ;ARRUELA LISA 8 MM - AÇÃO;UN\n"
    ";;\n"
).encode("cp1252")


def make_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Materiais"
    ws.append(["Relatório sintético de teste"])  # linha de título, não é cabeçalho
    ws.append(["Código", "Descrição", "Qtd"])
    ws.append(["000456", "Suporte SYN", 2])
    ws.append([789, "Suporte SYN 2", 4])  # número: perde zeros se houver
    ws.append(["000456", "Suporte SYN", 1])  # duplicata exata
    outra = wb.create_sheet("Outra")
    outra.append(["Chave", "Valor"])
    outra.append(["X1", 9])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def limits(**overrides: int | float) -> ImportLimits:
    return ImportLimits(**overrides)  # type: ignore[arg-type]


# ---------- domínio puro ----------


def test_code_key_preserves_leading_zeros_and_ignores_case_and_edges() -> None:
    assert code_key("  00123 ") == "00123"
    assert code_key("ab1") == code_key("AB1 ")
    assert code_key("00123") != code_key("123")


def test_normalize_description_removes_accents_and_case() -> None:
    assert normalize_description("  Ação  DE   Teste ") == "acao de teste"


def test_header_detection_skips_title_row() -> None:
    rows = [["Relatório sintético"], ["Código", "Descrição", "Qtd"], ["1", "A", "2"]]
    assert detect_header_index(rows) == 1


def test_unique_headers_fills_blanks_and_suffixes_repeats() -> None:
    assert unique_headers(["A", "", "A", "  "]) == ["A", "Coluna 2", "A (2)", "Coluna 4"]


def test_exact_duplicates_do_not_merge_leading_zero_variants() -> None:
    items = [(2, "00123"), (3, "0123"), (4, "00123"), (5, "ab1 "), (6, "AB1")]
    groups = exact_code_duplicates(items)
    keys = {g.key: g.row_numbers for g in groups}
    assert keys == {"00123": [2, 4], "AB1": [5, 6]}


def test_leading_zero_suspicions_are_only_suggestions() -> None:
    pairs = leading_zero_suspicions(["00123", "0123", "999"])
    assert [(p.key_a, p.key_b) for p in pairs] == [("00123", "0123")]


def test_similar_descriptions_report_score_and_evidence() -> None:
    items = [
        (2, "Parafuso M8 sextavado"),
        (3, "PARAFUSO M8 SEXTAVADO"),
        (4, "Porca M8 sextavada"),
        (5, "Arruela de aço"),
    ]
    pairs = similar_descriptions(items, threshold=0.85)
    assert pairs[0].row_a == 2 and pairs[0].row_b == 3
    assert pairs[0].score == 1.0
    assert "m8" in pairs[0].shared_tokens
    assert all(p.score >= 0.85 for p in pairs)
    assert not any(p.row_b == 5 for p in pairs)


def test_similar_descriptions_refuses_oversized_input() -> None:
    with pytest.raises(DomainError, match="limitada"):
        similar_descriptions([(i, f"item {i}") for i in range(10)], max_items=5)


def test_compare_codes_keeps_zero_variants_as_candidates_only() -> None:
    result = compare_codes(["00123", "0045", "X1"], ["123", "45", "X1"])
    assert result.in_both == ["X1"]
    assert result.only_left == ["00123", "0045"]
    assert result.only_right == ["123", "45"]
    assert ("00123", "123") in result.leading_zero_candidates
    assert ("0045", "45") in result.leading_zero_candidates


def test_validate_mapping_rejects_unknown_field_and_missing_column() -> None:
    with pytest.raises(DomainError, match="desconhecidos"):
        validate_mapping({"preco": "Código"}, ["Código"])
    with pytest.raises(DomainError, match="inexistentes"):
        validate_mapping({"code": "Inexistente"}, ["Código"])


# ---------- leitores ----------


def test_read_csv_detects_semicolon_and_cp1252_and_keeps_zeros() -> None:
    table = read_csv(CSV_CP1252, limits())
    assert table.columns == ["SYN-Código", "SYN-Descrição", "Unidade"]
    assert table.rows[0] == ["00123", "Parafuso M8 sextavado", "UN"]
    assert table.rows[3][1].startswith("Arruela lisa 8 mm")
    assert table.warnings == []
    assert all(any(cell for cell in row) for row in table.rows)  # linha vazia descartada


def test_read_xlsx_default_sheet_keeps_text_codes_and_warns_on_numbers() -> None:
    table = read_xlsx(make_xlsx(), None, limits())
    assert table.sheet == "Materiais"
    assert table.columns == ["Código", "Descrição", "Qtd"]
    assert table.rows[0][0] == "000456"  # texto preserva zeros
    assert table.rows[1][0] == "789"
    assert any("numérica" in w for w in table.warnings)


def test_read_xlsx_selects_named_sheet_and_rejects_unknown() -> None:
    table = read_xlsx(make_xlsx(), "Outra", limits())
    assert table.columns == ["Chave", "Valor"]
    with pytest.raises(DomainError, match="não existe"):
        read_xlsx(make_xlsx(), "Inexistente", limits())


def test_detect_kind_rejects_legacy_xls_and_binary() -> None:
    with pytest.raises(DomainError, match="xls"):
        detect_kind(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 10)
    with pytest.raises(DomainError, match="binário"):
        detect_kind(b"abc\x00def")
    assert detect_kind(b"Codigo;Desc\n1;a\n") == "csv"


def test_zip_bomb_like_xlsx_is_rejected() -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/bomb.xml", b"\x00" * (2 * 1024 * 1024))  # altíssima razão de compressão
    with pytest.raises(DomainError, match="zip bomb"):
        read_xlsx(payload.getvalue(), None, limits())


def test_row_limit_is_enforced() -> None:
    data = ("Código;Desc\n" + "".join(f"{i};x\n" for i in range(20))).encode("utf-8")
    with pytest.raises(DomainError, match="limite"):
        read_csv(data, limits(max_rows=5))


# ---------- persistência e idempotência ----------


@pytest.fixture
def storage(tmp_path: Path) -> Path:
    return tmp_path / "originals"


def test_import_is_idempotent_for_same_hash_and_sheet(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    storage: Path,
) -> None:
    with session_factory() as db:
        first = import_file(
            db,
            actor="t@example.com",
            filename="SYN-materiais.csv",
            data=CSV_CP1252,
            sheet=None,
            limits=limits(),
            storage_dir=storage,
            correlation_id="c1",
        )
        db.commit()
        assert first.created is True
        second = import_file(
            db,
            actor="t@example.com",
            filename="SYN-materiais.csv",
            data=CSV_CP1252,
            sheet=None,
            limits=limits(),
            storage_dir=storage,
            correlation_id="c2",
        )
        db.commit()
        assert second.created is False
        assert second.dataset.id == first.dataset.id
    assert (storage / next(storage.iterdir()).name).exists()


# ---------- API ----------


@pytest.fixture
def patched_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(
        database_url="sqlite:///unused",
        data_dir=str(tmp_path / "data"),
        max_upload_mb=1,
        max_rows=500_000,
    )
    monkeypatch.setattr("engiflow_api.presentation.routes.datasets.get_settings", lambda: settings)
    return settings


def _upload(client: TestClient, name: str, data: bytes, sheet: str | None = None) -> object:
    form: dict[str, str] = {}
    if sheet is not None:
        form["sheet"] = sheet
    return client.post(
        "/api/v1/datasets",
        files={"file": (name, data, "application/octet-stream")},
        data=form,
    )


def test_upload_requires_authentication(client: TestClient, patched_settings: Settings) -> None:
    resp = client.post("/api/v1/datasets", files={"file": ("a.csv", CSV_CP1252, "text/csv")})
    assert resp.status_code == 401


def test_upload_list_detail_and_rows_flow(
    logged_client: TestClient,
    patched_settings: Settings,
    session_factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    created = _upload(logged_client, "SYN-materiais.csv", CSV_CP1252)
    assert created.status_code == 201  # type: ignore[attr-defined]
    body = created.json()  # type: ignore[attr-defined]
    assert body["created"] is True
    dataset_id = body["dataset"]["id"]
    assert body["dataset"]["row_count"] == 5
    assert body["dataset"]["columns"][0] == "SYN-Código"

    again = _upload(logged_client, "SYN-materiais.csv", CSV_CP1252)
    assert again.status_code == 200  # type: ignore[attr-defined]
    assert again.json()["created"] is False  # type: ignore[attr-defined]

    listing = logged_client.get("/api/v1/datasets").json()
    assert [d["id"] for d in listing] == [dataset_id]

    detail = logged_client.get(f"/api/v1/datasets/{dataset_id}").json()
    assert detail["preview"][0]["SYN-Código"] == "00123"

    rows = logged_client.get(f"/api/v1/datasets/{dataset_id}/rows?offset=1&limit=2").json()
    assert rows["total"] == 5
    assert [r["row_number"] for r in rows["rows"]] == [3, 4]

    with session_factory() as db:
        actions = db.scalars(select(AuditLog.action)).all()
        assert "data_studio.import" in actions


def test_mapping_then_duplicates_and_compare(
    logged_client: TestClient, patched_settings: Settings
) -> None:
    first = _upload(logged_client, "SYN-a.csv", CSV_CP1252).json()  # type: ignore[attr-defined]
    xlsx = _upload(logged_client, "SYN-b.xlsx", make_xlsx(), sheet="Materiais").json()  # type: ignore[attr-defined]
    left_id = first["dataset"]["id"]
    right_id = xlsx["dataset"]["id"]

    no_mapping = logged_client.post(
        "/api/v1/datasets/compare", json={"left_id": left_id, "right_id": right_id}
    )
    assert no_mapping.status_code == 422
    assert no_mapping.json()["title"] == "Regra de negócio"

    put = logged_client.put(
        f"/api/v1/datasets/{left_id}/mapping",
        json={"mapping": {"code": "SYN-Código", "description": "SYN-Descrição"}},
    )
    assert put.status_code == 200
    logged_client.put(
        f"/api/v1/datasets/{right_id}/mapping",
        json={"mapping": {"code": "Código", "description": "Descrição"}},
    )

    dups = logged_client.get(f"/api/v1/datasets/{left_id}/duplicates?threshold=0.85").json()
    keys = {g["key"]: g["row_numbers"] for g in dups["exact_codes"]}
    assert keys == {"00123": [2, 4], "AB1": [5, 6]}
    assert any(
        s["key_a"] == "00123" and s["key_b"] == "0123" for s in dups["leading_zero_suspicions"]
    )
    assert dups["similar_descriptions"]  # descrições com mesmo texto normalizado
    assert "revisão humana" in dups["note"]

    cmp = logged_client.post(
        "/api/v1/datasets/compare", json={"left_id": left_id, "right_id": right_id}
    ).json()
    # Esquerda: 00123, 0123, AB1. Direita (planilha): 000456, 789. Sem interseção.
    assert cmp["only_left_count"] == 3
    assert cmp["only_right"] == ["000456", "789"]
    assert cmp["in_both_count"] == 0
    assert cmp["leading_zero_candidates"] == []


def test_mapping_rejects_unknown_column(
    logged_client: TestClient, patched_settings: Settings
) -> None:
    dataset_id = _upload(logged_client, "SYN-c.csv", CSV_CP1252).json()["dataset"]["id"]  # type: ignore[attr-defined]
    resp = logged_client.put(
        f"/api/v1/datasets/{dataset_id}/mapping", json={"mapping": {"code": "NaoExiste"}}
    )
    assert resp.status_code == 422


def test_upload_over_limit_is_rejected(
    logged_client: TestClient, patched_settings: Settings
) -> None:
    big = b"Codigo;Desc\n" + b"1;" + b"x" * (1024 * 1024 + 10)
    resp = _upload(logged_client, "SYN-grande.csv", big)
    assert resp.status_code == 422  # type: ignore[attr-defined]
    assert "limite" in resp.json()["detail"]  # type: ignore[attr-defined]
