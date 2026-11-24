"""Data Studio: leitura CSV/XLSX, mapeamento, duplicatas, comparação e exportação.

Todas as fixtures são SINTÉTICAS (prefixo SYN-), geradas em código. Nenhum dado real.
"""

from __future__ import annotations

import hashlib
import inspect
import io
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from engiflow_api.application import data_studio as ds
from engiflow_api.core.config import Settings
from engiflow_api.domain import tabular
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
from engiflow_api.infrastructure.exporters import Sheet, to_csv_bytes, to_xlsx_bytes
from engiflow_api.infrastructure.models import AuditLog, Dataset, DatasetVersionRow
from engiflow_api.infrastructure.readers import (
    ImportLimits,
    detect_kind_file,
    open_csv,
    open_xlsx,
)

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


@dataclass
class Loaded:
    columns: list[str]
    rows: list[list[str | None]]
    row_numbers: list[int]
    sheet: str | None
    warnings: list[str]


def _load(
    data: bytes,
    *,
    xlsx: bool = False,
    sheet: str | None = None,
    lim: ImportLimits | None = None,
) -> Loaded:
    """Lê bytes pelo mesmo caminho de produção (arquivo em disco + streaming)."""
    active = lim or limits()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ("f.xlsx" if xlsx else "f.csv")
        path.write_bytes(data)
        ctx = open_xlsx(path, sheet, active) if xlsx else open_csv(path, active)
        with ctx as stream:
            pairs = list(stream.rows)
        return Loaded(
            columns=stream.columns,
            rows=[values for _, values in pairs],
            row_numbers=[number for number, _ in pairs],
            sheet=stream.sheet,
            warnings=stream.warnings,
        )


def _kind(data: bytes) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "f.bin"
        path.write_bytes(data)
        return detect_kind_file(path)


# ---------- domínio puro ----------


def test_code_key_preserves_leading_zeros_and_ignores_case_and_edges() -> None:
    assert code_key("  00123 ") == "00123"
    assert code_key("ab1") == code_key("AB1 ")
    assert code_key("00123") != code_key("123")


def test_normalize_description_removes_accents_case_and_punctuation() -> None:
    assert normalize_description("  Ação  DE   Teste ") == "acao de teste"
    assert normalize_description("PARAFUSO M8-SEXTAVADO") == "parafuso m8 sextavado"


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
    table = _load(CSV_CP1252)
    assert table.columns == ["SYN-Código", "SYN-Descrição", "Unidade"]
    assert table.rows[0] == ["00123", "Parafuso M8 sextavado", "UN"]
    assert (table.rows[3][1] or "").startswith("Arruela lisa 8 mm")
    assert table.warnings == []
    assert all(any(cell for cell in row) for row in table.rows)  # linha vazia descartada


def test_read_xlsx_default_sheet_keeps_text_codes_and_warns_on_numbers() -> None:
    table = _load(make_xlsx(), xlsx=True)
    assert table.sheet == "Materiais"
    assert table.columns == ["Código", "Descrição", "Qtd"]
    assert table.rows[0][0] == "000456"  # texto preserva zeros
    assert table.rows[1][0] == "789"
    assert any("numérica" in w for w in table.warnings)


def test_read_xlsx_selects_named_sheet_and_rejects_unknown() -> None:
    table = _load(make_xlsx(), xlsx=True, sheet="Outra")
    assert table.columns == ["Chave", "Valor"]
    with pytest.raises(DomainError, match="não existe"):
        _load(make_xlsx(), xlsx=True, sheet="Inexistente")


def test_detect_kind_rejects_legacy_xls_and_binary() -> None:
    with pytest.raises(DomainError, match="xls"):
        _kind(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 10)
    with pytest.raises(DomainError, match="binário"):
        _kind(b"abc\x00def")
    assert _kind(b"Codigo;Desc\n1;a\n") == "csv"


def test_zip_bomb_like_xlsx_is_rejected() -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/bomb.xml", b"\x00" * (2 * 1024 * 1024))  # altíssima razão de compressão
    with pytest.raises(DomainError, match="zip bomb"):
        _load(payload.getvalue(), xlsx=True)


def test_row_limit_is_enforced() -> None:
    data = ("Código;Desc\n" + "".join(f"{i};x\n" for i in range(20))).encode("utf-8")
    with pytest.raises(DomainError, match="limite"):
        _load(data, lim=limits(max_rows=5))


# ---------- persistência e idempotência ----------


@pytest.fixture
def storage(tmp_path: Path) -> Path:
    path = tmp_path / "originals"
    path.mkdir()
    return path


def _import(
    db: DbSession,
    storage: Path,
    data: bytes,
    *,
    sheet: str | None = None,
    lim: ImportLimits | None = None,
    name: str = "SYN-materiais.csv",
) -> ds.ImportResult:
    temp = storage / f".tmp-{uuid.uuid4().hex}"
    temp.write_bytes(data)
    return ds.import_upload(
        db,
        actor="t@example.com",
        filename=name,
        temp_path=temp,
        digest=hashlib.sha256(data).hexdigest(),
        sheet=sheet,
        limits=lim or limits(),
        storage_dir=storage,
        correlation_id="c1",
    )


def test_import_is_idempotent_for_same_hash_and_sheet(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    storage: Path,
) -> None:
    with session_factory() as db:
        first = _import(db, storage, CSV_CP1252)
        assert first.created is True
        second = _import(db, storage, CSV_CP1252)
        assert second.created is False
        assert second.dataset.id == first.dataset.id
    finals = [p for p in storage.iterdir() if not p.name.startswith(".tmp-")]
    assert len(finals) == 1
    assert not [p for p in storage.iterdir() if p.name.startswith(".tmp-")]


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


def _mapped_pair(logged_client: TestClient) -> tuple[str, str]:
    first = _upload(logged_client, "SYN-a.csv", CSV_CP1252).json()  # type: ignore[attr-defined]
    xlsx = _upload(logged_client, "SYN-b.xlsx", make_xlsx(), sheet="Materiais").json()  # type: ignore[attr-defined]
    left_id = first["dataset"]["id"]
    right_id = xlsx["dataset"]["id"]
    logged_client.put(
        f"/api/v1/datasets/{left_id}/mapping",
        json={"mapping": {"code": "SYN-Código", "description": "SYN-Descrição"}},
    )
    logged_client.put(
        f"/api/v1/datasets/{right_id}/mapping",
        json={"mapping": {"code": "Código", "description": "Descrição"}},
    )
    return left_id, right_id


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

    logged_client.put(
        f"/api/v1/datasets/{left_id}/mapping",
        json={"mapping": {"code": "SYN-Código", "description": "SYN-Descrição"}},
    )
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
    assert dups["similar_descriptions"]
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


# =====================================================================
# REGRESSÕES DA REVISÃO TÉCNICA (Fase 2, revisão 1)
# =====================================================================

# ---------- 1. comparação por zeros à esquerda não perde candidatos ----------


def test_regression_candidates_not_lost_when_right_has_several_variants() -> None:
    """Antes: só uma variante por grupo era guardada; '0123' e '123' se perdiam."""
    result = compare_codes(["00123"], ["123", "0123"])
    assert ("00123", "0123") in result.leading_zero_candidates
    assert ("00123", "123") in result.leading_zero_candidates


def test_regression_candidates_found_against_keys_present_on_both_sides() -> None:
    """Antes: só comparava contra chaves exclusivas do outro lado; '123' (em ambos) se perdia."""
    result = compare_codes(["00123", "123"], ["123"])
    assert result.in_both == ["123"]
    assert ("00123", "123") in result.leading_zero_candidates


def test_regression_all_zero_codes_are_compared() -> None:
    """Antes: '000' tinha chave de grupo vazia e nunca era comparado com '0'."""
    result = compare_codes(["000"], ["0"])
    assert ("000", "0") in result.leading_zero_candidates
    suspicions = leading_zero_suspicions(["000", "0"])
    assert [(s.key_a, s.key_b) for s in suspicions] == [("0", "000")]


def test_regression_api_compare_returns_every_candidate_without_truncation(
    logged_client: TestClient, patched_settings: Settings
) -> None:
    """Antes: a API cortava as listas em 1000 itens. Aqui são 1100 candidatos."""
    total = 1100
    left_csv = ("Código;Desc\n" + "".join(f"0{i};x\n" for i in range(1, total + 1))).encode("utf-8")
    right_csv = ("Código;Desc\n" + "".join(f"{i};x\n" for i in range(1, total + 1))).encode("utf-8")
    left = _upload(logged_client, "SYN-esq.csv", left_csv).json()  # type: ignore[attr-defined]
    right = _upload(logged_client, "SYN-dir.csv", right_csv).json()  # type: ignore[attr-defined]
    for dataset in (left, right):
        logged_client.put(
            f"/api/v1/datasets/{dataset['dataset']['id']}/mapping",
            json={"mapping": {"code": "Código"}},
        )
    body = logged_client.post(
        "/api/v1/datasets/compare",
        json={"left_id": left["dataset"]["id"], "right_id": right["dataset"]["id"]},
    ).json()
    assert len(body["leading_zero_candidates"]) == total
    assert body["in_both_count"] == 0
    assert len(body["only_left"]) == total


# ---------- 2. memória: leitura em streaming, lotes e linhas com limite ----------


def test_regression_csv_rows_are_a_lazy_generator_not_a_list(tmp_path: Path) -> None:
    """A leitura não materializa o arquivo: as linhas são um gerador consumido sob demanda."""
    path = tmp_path / "f.csv"
    path.write_bytes(CSV_CP1252)
    with open_csv(path, limits()) as stream:
        assert inspect.isgenerator(stream.rows)
        first = next(stream.rows)
        assert first[0] == 2  # primeira linha de dados na origem


def test_regression_file_handle_is_closed_after_stream(tmp_path: Path) -> None:
    path = tmp_path / "f.csv"
    path.write_bytes(CSV_CP1252)
    with open_csv(path, limits()) as stream:
        list(stream.rows)
    # No Windows, um arquivo aberto não pode ser removido. Remover prova que foi fechado.
    path.unlink()
    assert not path.exists()


def test_regression_large_import_is_written_in_batches(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Antes: uma única lista de objetos para todas as linhas. Agora: lotes de INSERT_BATCH_SIZE."""
    monkeypatch.setattr(ds, "INSERT_BATCH_SIZE", 3)
    calls: list[int] = []

    data = ("Código;Desc\n" + "".join(f"{i};x{i}\n" for i in range(1, 8))).encode("utf-8")
    with session_factory() as db:
        real_execute = db.execute

        def counting_execute(
            statement: object, params: object = None, *a: object, **k: object
        ) -> object:
            if isinstance(params, list):
                calls.append(len(params))
            return real_execute(statement, params, *a, **k)

        monkeypatch.setattr(db, "execute", counting_execute)
        result = _import(db, storage, data)
        assert result.created is True
    assert calls == [3, 3, 1]


# ---------- 3. similaridade independente da ordem dos termos ----------


def test_regression_word_order_does_not_hide_similar_descriptions() -> None:
    """Antes: 'M8 PARAFUSO' e 'PARAFUSO M8' tinham prefixos diferentes e nunca eram comparados."""
    pairs = similar_descriptions([(2, "M8 PARAFUSO"), (3, "PARAFUSO M8")], threshold=0.85)
    assert len(pairs) == 1
    assert pairs[0].score == 1.0
    assert pairs[0].reason == "mesmos termos em outra ordem"
    assert pairs[0].shared_tokens == ["m8", "parafuso"]


def test_regression_pair_found_through_a_shared_token_with_different_prefix() -> None:
    pairs = similar_descriptions(
        [(2, "Sextavado parafuso aço M8"), (3, "Parafuso aço M8 sextavado")], threshold=0.85
    )
    assert pairs and pairs[0].reason == "mesmos termos em outra ordem"


def test_regression_punctuation_does_not_reduce_score() -> None:
    pairs = similar_descriptions([(2, "PARAFUSO M8-SEXTAVADO"), (3, "parafuso m8 sextavado")])
    assert pairs[0].score == 1.0


def test_regression_common_token_does_not_generate_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token muito frequente é ignorado para gerar candidatos (limite documentado)."""
    monkeypatch.setattr(tabular, "MAX_TOKEN_DOCUMENT_FREQUENCY", 2)
    items = [(i, f"peca comum item{i}") for i in range(1, 6)]
    assert similar_descriptions(items, threshold=0.5) == []
    rare = [(1, "alpha beta"), (2, "beta alpha"), (3, "gama")]
    assert similar_descriptions(rare, threshold=0.5)[0].reason == "mesmos termos em outra ordem"


# ---------- 4. consistência entre arquivo e transação ----------


def _count_datasets(session_factory: sessionmaker) -> int:  # type: ignore[type-arg]
    with session_factory() as db:
        return int(db.scalar(select(func.count()).select_from(Dataset)) or 0)


def _final_files(storage: Path) -> list[Path]:
    return [p for p in storage.iterdir() if not p.name.startswith(".tmp-")]


def test_regression_failed_parse_leaves_no_dataset_no_file_no_temp(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    storage: Path,
) -> None:
    data = ("Código;Desc\n" + "".join(f"{i};x\n" for i in range(10))).encode("utf-8")
    with session_factory() as db, pytest.raises(DomainError, match="limite"):
        _import(db, storage, data, lim=limits(max_rows=3))
    assert _count_datasets(session_factory) == 0
    assert _final_files(storage) == []
    assert list(storage.iterdir()) == []


def test_regression_commit_failure_removes_new_file_and_rows(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Antes: o arquivo era gravado antes da transação e ficava órfão se o commit falhasse."""
    with session_factory() as db:
        monkeypatch.setattr(db, "commit", _raise_runtime)
        with pytest.raises(RuntimeError, match="falha simulada"):
            _import(db, storage, CSV_CP1252)
    assert _count_datasets(session_factory) == 0
    assert _final_files(storage) == []
    assert list(storage.iterdir()) == []
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(DatasetVersionRow)) == 0


def test_regression_commit_failure_keeps_file_that_already_existed(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Um arquivo final que já existia nunca é removido por uma falha posterior."""
    digest = hashlib.sha256(CSV_CP1252).hexdigest()
    preexisting = storage / f"{digest}.csv"
    preexisting.write_bytes(CSV_CP1252)
    with session_factory() as db:
        monkeypatch.setattr(db, "commit", _raise_runtime)
        with pytest.raises(RuntimeError, match="falha simulada"):
            _import(db, storage, CSV_CP1252)
    assert preexisting.exists()


def _raise_runtime() -> None:
    raise RuntimeError("falha simulada")


def test_regression_import_is_stored_only_after_rows_are_written(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    storage: Path,
) -> None:
    """Arquivo final e registro no banco aparecem juntos: após sucesso, ambos existem."""
    with session_factory() as db:
        result = _import(db, storage, CSV_CP1252)
        assert result.created is True
    assert _count_datasets(session_factory) == 1
    finals = _final_files(storage)
    assert len(finals) == 1
    assert finals[0].name == f"{hashlib.sha256(CSV_CP1252).hexdigest()}.csv"


# ---------- 5. exportação CSV e XLSX com códigos como texto ----------


def test_regression_csv_export_keeps_codes_and_neutralizes_formulas() -> None:
    content = to_csv_bytes(
        ["Código", "Desc"],
        [["00123", "a"], ["=1+1", "b"], ["-0123", "c"], ["-abc", "d"], ["+5", "e"]],
    )
    text = content.decode("utf-8-sig")
    assert text.splitlines()[0] == "Código;Desc"
    assert "00123;a" in text
    assert "'=1+1;b" in text
    assert "-0123;c" in text  # código numérico com sinal não é alterado
    assert "'-abc;d" in text
    assert "'+5;e" in text


def test_regression_xlsx_export_stores_codes_as_text_never_formulas(tmp_path: Path) -> None:
    content = to_xlsx_bytes(
        [Sheet("Dados", ["Código", "Desc"], [["000456", "a"], ["=SUM(A1)", "b"], ["789", "c"]])]
    )
    path = tmp_path / "out.xlsx"
    path.write_bytes(content)
    workbook = load_workbook(path)
    ws = workbook["Dados"]
    code = ws["A2"]
    assert code.value == "000456"
    assert code.data_type == "s"
    assert code.number_format == "@"
    formula_like = ws["A3"]
    assert formula_like.value == "=SUM(A1)"
    assert formula_like.data_type == "s"
    assert ws["A4"].value == "789"
    assert ws["A4"].data_type == "s"


def test_regression_xlsx_sheet_titles_are_valid_and_unique() -> None:
    long = "x" * 40
    content = to_xlsx_bytes([Sheet(long, ["A"], []), Sheet(long, ["A"], [])])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.xlsx"
        path.write_bytes(content)
        names = load_workbook(path).sheetnames
    assert len(names) == 2 and len(set(names)) == 2
    assert all(len(n) <= 31 for n in names)


def test_regression_export_endpoints_return_attachments(
    logged_client: TestClient, patched_settings: Settings
) -> None:
    left_id, right_id = _mapped_pair(logged_client)

    csv_resp = logged_client.get(f"/api/v1/datasets/{left_id}/export?format=csv")
    assert csv_resp.status_code == 200
    assert "attachment" in csv_resp.headers["content-disposition"]
    assert csv_resp.content.decode("utf-8-sig").splitlines()[1].startswith("00123;")

    xlsx_resp = logged_client.get(f"/api/v1/datasets/{right_id}/export?format=xlsx")
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert xlsx_resp.content[:2] == b"PK"

    dup_csv = logged_client.get(f"/api/v1/datasets/{left_id}/duplicates/export?format=csv")
    assert dup_csv.status_code == 200
    assert "codigo_repetido" in dup_csv.content.decode("utf-8-sig")
    dup_xlsx = logged_client.get(f"/api/v1/datasets/{left_id}/duplicates/export?format=xlsx")
    assert dup_xlsx.status_code == 200

    cmp_csv = logged_client.post(
        "/api/v1/datasets/compare/export?format=csv",
        json={"left_id": left_id, "right_id": right_id},
    )
    assert cmp_csv.status_code == 200
    assert "somente_A" in cmp_csv.content.decode("utf-8-sig")
    cmp_xlsx = logged_client.post(
        "/api/v1/datasets/compare/export?format=xlsx",
        json={"left_id": left_id, "right_id": right_id},
    )
    assert cmp_xlsx.status_code == 200


def test_regression_export_requires_authentication(
    client: TestClient, patched_settings: Settings
) -> None:
    resp = client.get("/api/v1/datasets/qualquer/export?format=csv")
    assert resp.status_code == 401


def test_regression_export_rejects_unknown_format(
    logged_client: TestClient, patched_settings: Settings
) -> None:
    left_id, _ = _mapped_pair(logged_client)
    resp = logged_client.get(f"/api/v1/datasets/{left_id}/export?format=pdf")
    assert resp.status_code == 422


# ---------- 6. CSV de exportação preserva zeros quando reimportado ----------


def test_regression_exported_csv_reimports_with_zeros_intact(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    storage: Path,
) -> None:
    content = to_csv_bytes(["Código", "Desc"], [["00123", "a"], ["0045", "b"]])
    table = _load(content)
    assert table.rows == [["00123", "a"], ["0045", "b"]]
