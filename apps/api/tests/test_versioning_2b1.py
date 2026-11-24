"""Fase 2B.1: versionamento, prévias, histórico, desfazer/refazer e concorrência.

Dados SINTÉTICOS (prefixo SYN-). Itens que dependem de PostgreSQL rodam no CI quando
ENGIFLOW_TEST_DATABASE_URL está definida (ver FASE_2B1_STATUS.md).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from engiflow_api.application import versioning
from engiflow_api.application.operations.registry import (
    OPERATIONS,
    RenameColumnParams,
    Snapshot,
    get_operation,
    validate_params,
)
from engiflow_api.core.config import Settings, get_settings
from engiflow_api.domain.canonical import CanonicalHasher, content_sha256
from engiflow_api.domain.errors import ConflictError, DomainError
from engiflow_api.infrastructure.models import (
    Base,
    Dataset,
    DatasetPreview,
    DatasetVersion,
    DatasetVersionRow,
)

SYN_CSV = (
    "SYN-Código;SYN-Descrição;Qtd\n00123;SYN parafuso;1\n0123;SYN porca;\nAB1;SYN arruela;7\n"
).encode()


# ---------- hash canônico ----------


def test_canonical_hash_is_stable_and_pinned() -> None:
    """Vetor fixo: qualquer mudança de serialização quebra este teste de propósito."""
    expected_bytes = (
        '{"columns":["Código","Qtd"],"schema":1}\n["00123","1"]\n["0",null]\n["","7"]\n'
    ).encode()
    expected = hashlib.sha256(expected_bytes).hexdigest()
    assert content_sha256(["Código", "Qtd"], [["00123", "1"], ["0", None], ["", "7"]]) == expected


def test_canonical_distinguishes_unknown_empty_and_zero() -> None:
    cols = ["Qtd"]
    unknown = content_sha256(cols, [[None]])
    empty = content_sha256(cols, [[""]])
    zero = content_sha256(cols, [["0"]])
    assert len({unknown, empty, zero}) == 3


def test_canonical_hash_changes_with_column_name_and_value() -> None:
    base = content_sha256(["A"], [["1"]])
    assert content_sha256(["B"], [["1"]]) != base
    assert content_sha256(["A"], [["2"]]) != base


def test_canonical_normalizes_unicode_nfc() -> None:
    decomposed = "Ac\u0327a\u0303o"  # "Ação" em NFD
    composed = "A\u00e7\u00e3o"  # "Ação" em NFC
    assert decomposed != composed
    assert content_sha256(["Descrição"], [[decomposed]]) == content_sha256(
        ["Descrição"], [[composed]]
    )


def test_streaming_hasher_matches_one_shot() -> None:
    rows: list[list[str | None]] = [["00123", "a"], ["0", None]]
    hasher = CanonicalHasher(["C", "D"])
    for row in rows:
        hasher.add_row(row)
    assert hasher.hexdigest() == content_sha256(["C", "D"], rows)


# ---------- registro e operações puras ----------


def _snap() -> Snapshot:
    return Snapshot(
        columns=["Código", "Descrição", "Qtd"],
        rows=[["00123", "parafuso M8", "1"], ["0123", "Parafuso M8", None], ["AB1", "", "7"]],
        row_numbers=[2, 3, 4],
    )


def test_registry_lists_the_three_minimal_operations() -> None:
    assert set(OPERATIONS) == {"rename_column", "replace_text", "set_rows_value"}
    with pytest.raises(DomainError, match="desconhecida"):
        get_operation("eval_python")


def test_params_forbid_unknown_fields() -> None:
    spec = get_operation("rename_column")
    with pytest.raises(DomainError, match="inválidos"):
        validate_params(spec, {"from_name": "A", "to_name": "B", "extra": 1})


def test_rename_refuses_collision_ignoring_case_and_keeps_rows() -> None:
    snap = _snap()
    with pytest.raises(DomainError, match="Já existe"):
        get_operation("rename_column").apply(
            snap, RenameColumnParams(from_name="Qtd", to_name="código")
        )
    result = get_operation("rename_column").apply(
        snap, RenameColumnParams(from_name="Qtd", to_name="Quantidade")
    )
    assert result.snapshot.columns[2] == "Quantidade"
    assert result.snapshot.rows == snap.rows
    assert result.cells_changed == 0


def test_replace_text_respects_case_and_leaves_unknown_untouched() -> None:
    spec = get_operation("replace_text")
    params = validate_params(
        spec, {"column": "Descrição", "find": "parafuso", "replace": "PARAF.", "match_case": False}
    )
    result = spec.apply(_snap(), params)
    assert result.snapshot.rows[0][1] == "PARAF. M8"
    assert result.snapshot.rows[1][1] == "PARAF. M8"
    assert result.cells_changed == 2


def test_replace_text_whole_cell_only_matches_full_value() -> None:
    spec = get_operation("replace_text")
    params = validate_params(
        spec, {"column": "Qtd", "find": "1", "replace": "um", "whole_cell": True}
    )
    result = spec.apply(_snap(), params)
    assert result.snapshot.rows[0][2] == "um"
    assert result.snapshot.rows[2][2] == "7"
    assert result.snapshot.rows[1][2] is None  # desconhecido não é substituído


def test_set_rows_value_distinguishes_empty_unknown_and_text() -> None:
    spec = get_operation("set_rows_value")
    empty = spec.apply(
        _snap(), validate_params(spec, {"row_numbers": [2], "column": "Qtd", "value": ""})
    )
    unknown = spec.apply(
        _snap(), validate_params(spec, {"row_numbers": [2], "column": "Qtd", "value": None})
    )
    assert empty.snapshot.rows[0][2] == ""
    assert unknown.snapshot.rows[0][2] is None
    assert empty.snapshot.rows[0][2] != unknown.snapshot.rows[0][2]


def test_set_rows_value_refuses_missing_rows_and_touches_only_selection() -> None:
    spec = get_operation("set_rows_value")
    with pytest.raises(DomainError, match="inexistentes"):
        spec.apply(
            _snap(), validate_params(spec, {"row_numbers": [2, 99], "column": "Qtd", "value": "0"})
        )
    result = spec.apply(
        _snap(), validate_params(spec, {"row_numbers": [4], "column": "Qtd", "value": "9"})
    )
    assert result.snapshot.rows[2][2] == "9"
    assert result.snapshot.rows[0] == _snap().rows[0]  # linha fora da seleção intacta


# ---------- API: fluxo completo ----------


@pytest.fixture
def storage_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(
        database_url="sqlite:///unused",
        data_dir=str(tmp_path / "data"),
        max_upload_mb=5,
        max_rows=500_000,
    )
    monkeypatch.setattr("engiflow_api.presentation.routes.datasets.get_settings", lambda: settings)
    monkeypatch.setattr(
        "engiflow_api.presentation.routes.operations.get_settings", lambda: settings, raising=False
    )
    return settings


def _import(client: TestClient, data: bytes = SYN_CSV) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": ("SYN-v.csv", data, "text/csv")})
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    dataset: dict[str, Any] = body["dataset"]
    return dataset


def _versions(client: TestClient, dataset_id: str) -> list[dict[str, Any]]:
    body: list[dict[str, Any]] = client.get(f"/api/v1/datasets/{dataset_id}/versions").json()
    return body


def _current(client: TestClient, dataset_id: str) -> str:
    current: str = next(v["id"] for v in _versions(client, dataset_id) if v["is_current"])
    return current


def _preview(
    client: TestClient, dataset_id: str, code: str, params: dict[str, Any], base: str
) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/datasets/{dataset_id}/operations/preview",
        json={"code": code, "params": params, "base_version_id": base},
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _apply(
    client: TestClient, dataset_id: str, preview_id: str, base: str, key: str | None = None
) -> Any:
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        f"/api/v1/datasets/{dataset_id}/operations",
        json={"preview_id": preview_id, "base_version_id": base},
        headers=headers,
    )


def _rows(client: TestClient, dataset_id: str) -> list[list[str | None]]:
    body = client.get(f"/api/v1/datasets/{dataset_id}/rows?limit=500").json()
    return [r["values"] for r in body["rows"]]


def test_catalog_endpoint_exposes_schemas(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    body = logged_client.get("/api/v1/operations/catalog").json()
    codes = {item["code"] for item in body}
    assert codes == {"rename_column", "replace_text", "set_rows_value"}
    assert all("properties" in item["params_schema"] for item in body)


def test_import_creates_version_one_with_content_hash(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    versions = _versions(logged_client, ds["id"])
    assert len(versions) == 1
    assert versions[0]["number"] == 1 and versions[0]["is_current"] is True
    assert versions[0]["content_sha256"] == content_sha256(
        ds["columns"],
        [["00123", "SYN parafuso", "1"], ["0123", "SYN porca", ""], ["AB1", "SYN arruela", "7"]],
    )


def test_preview_changes_nothing_and_apply_creates_new_version(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    original_file = list((Path(storage_settings.data_dir) / "originals").glob("*.csv"))[0]
    file_hash_before = hashlib.sha256(original_file.read_bytes()).hexdigest()

    prev = _preview(
        logged_client,
        ds["id"],
        "replace_text",
        {"column": "SYN-Descrição", "find": "SYN", "replace": "PÇ"},
        base,
    )
    assert len(_versions(logged_client, ds["id"])) == 1  # prévia não cria versão
    assert _rows(logged_client, ds["id"])[0][0] == "00123"

    resp = _apply(logged_client, ds["id"], prev["preview_id"], base)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] is True
    assert body["content_sha256"] == prev["after_content_sha256"]  # prévia == aplicação
    assert body["current_version_id"] != base
    assert _rows(logged_client, ds["id"])[0] == ["00123", "PÇ parafuso", "1"]
    assert _rows(logged_client, ds["id"])[0][0] == "00123"  # zeros preservados
    assert (
        hashlib.sha256(original_file.read_bytes()).hexdigest() == file_hash_before
    )  # original intacto


def test_preview_is_single_use_and_apply_requires_same_base(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    prev = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "5"},
        base,
    )
    assert _apply(logged_client, ds["id"], prev["preview_id"], base).status_code == 201
    again = _apply(logged_client, ds["id"], prev["preview_id"], base)
    assert again.status_code == 409  # prévia já usada (ou base mudou)


def test_stale_base_is_a_conflict_and_nothing_changes(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    prev = _preview(
        logged_client, ds["id"], "rename_column", {"from_name": "Qtd", "to_name": "Quant"}, base
    )
    prev2 = _preview(
        logged_client,
        ds["id"],
        "rename_column",
        {"from_name": "SYN-Descrição", "to_name": "Desc"},
        base,
    )
    assert _apply(logged_client, ds["id"], prev["preview_id"], base).status_code == 201
    stale = _apply(logged_client, ds["id"], prev2["preview_id"], base)
    assert stale.status_code == 409
    assert len(_versions(logged_client, ds["id"])) == 2


def test_idempotency_key_replays_the_same_result(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    prev = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [4], "column": "Qtd", "value": None},
        base,
    )
    first = _apply(logged_client, ds["id"], prev["preview_id"], base, key="chave-1")
    assert first.status_code == 201
    replay = _apply(logged_client, ds["id"], prev["preview_id"], base, key="chave-1")
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert replay.json()["operation"]["id"] == first.json()["operation"]["id"]
    assert len(_versions(logged_client, ds["id"])) == 2  # sem versão extra


def test_undo_and_redo_move_the_pointer_without_deleting_history(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    v1 = _current(logged_client, ds["id"])
    prev = _preview(
        logged_client,
        ds["id"],
        "replace_text",
        {"column": "Qtd", "find": "7", "replace": "70", "whole_cell": True},
        v1,
    )
    v2 = _apply(logged_client, ds["id"], prev["preview_id"], v1).json()["current_version_id"]

    undone = logged_client.post(f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": v2})
    assert undone.status_code == 200 and undone.json()["current_version_id"] == v1
    assert _rows(logged_client, ds["id"])[2][2] == "7"
    ops = logged_client.get(f"/api/v1/datasets/{ds['id']}/operations").json()
    assert [o["status"] for o in ops] == ["undone"]
    assert len(_versions(logged_client, ds["id"])) == 2  # histórico preservado

    redone = logged_client.post(f"/api/v1/datasets/{ds['id']}/redo", json={"base_version_id": v1})
    assert redone.json()["current_version_id"] == v2
    assert _rows(logged_client, ds["id"])[2][2] == "70"


def test_undo_with_stale_base_and_nothing_to_undo(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    v1 = _current(logged_client, ds["id"])
    nothing = logged_client.post(f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": v1})
    assert nothing.status_code == 422
    prev = _preview(
        logged_client, ds["id"], "rename_column", {"from_name": "Qtd", "to_name": "Q"}, v1
    )
    v2 = _apply(logged_client, ds["id"], prev["preview_id"], v1).json()["current_version_id"]
    stale = logged_client.post(f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": v1})
    assert stale.status_code == 409
    assert _current(logged_client, ds["id"]) == v2


def test_rename_updates_columns_and_mapping_and_undo_restores(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    logged_client.put(
        f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": "SYN-Código"}}
    )
    v1 = _current(logged_client, ds["id"])
    prev = _preview(
        logged_client,
        ds["id"],
        "rename_column",
        {"from_name": "SYN-Código", "to_name": "Código"},
        v1,
    )
    v2 = _apply(logged_client, ds["id"], prev["preview_id"], v1).json()["current_version_id"]
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert "Código" in detail["columns"] and detail["mapping"]["code"] == "Código"
    logged_client.post(f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": v2})
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert "SYN-Código" in detail["columns"] and detail["mapping"]["code"] == "SYN-Código"


def test_unknown_rows_and_expired_preview_are_refused(
    logged_client: TestClient,
    storage_settings: Settings,
    session_factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    bad = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/operations/preview",
        json={
            "code": "set_rows_value",
            "params": {"row_numbers": [999], "column": "Qtd", "value": "1"},
            "base_version_id": base,
        },
    )
    assert bad.status_code == 422

    prev = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "3"},
        base,
    )
    with session_factory() as db:
        row = db.get(DatasetPreview, prev["preview_id"])
        assert row is not None
        row.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
        db.commit()
    assert _apply(logged_client, ds["id"], prev["preview_id"], base).status_code == 422


def test_history_lists_applied_operations_in_order(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    p1 = _preview(
        logged_client, ds["id"], "rename_column", {"from_name": "Qtd", "to_name": "Q"}, base
    )
    v1 = _apply(logged_client, ds["id"], p1["preview_id"], base).json()["current_version_id"]
    p2 = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Q", "value": "9"},
        v1,
    )
    _apply(logged_client, ds["id"], p2["preview_id"], v1)
    ops = logged_client.get(f"/api/v1/datasets/{ds['id']}/operations").json()
    assert [o["code"] for o in ops] == ["rename_column", "set_rows_value"]
    assert [o["seq"] for o in ops] == [1, 2]
    assert all(o["status"] == "applied" for o in ops)


def test_operations_require_authentication(client: TestClient, storage_settings: Settings) -> None:
    assert client.get("/api/v1/operations/catalog").status_code == 401


# ---------- concorrência ----------


def test_concurrent_applications_on_same_base_create_one_version(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    tmp_path: Path,
) -> None:
    """Duas aplicações simultâneas, prévias distintas, mesma base: uma aplica, a outra é recusada.

    Roda em PostgreSQL quando ENGIFLOW_TEST_DATABASE_URL está definida (CI); senão, em SQLite.
    """
    from engiflow_api.application import data_studio as ds_service
    from engiflow_api.infrastructure.readers import ImportLimits

    storage = tmp_path / "originals"
    storage.mkdir()
    temp = storage / f".tmp-{uuid.uuid4().hex}"
    temp.write_bytes(SYN_CSV)
    digest = hashlib.sha256(SYN_CSV).hexdigest()
    with session_factory() as db:
        ds_service.import_upload(
            db,
            actor="t@example.com",
            filename="SYN-c.csv",
            temp_path=temp,
            digest=digest,
            sheet=None,
            limits=ImportLimits(),
            storage_dir=storage,
            correlation_id=None,
        )
        db.commit()
        dataset = db.query(Dataset).one()
        base = dataset.current_version_id
        assert base is not None
        prev_a = versioning.create_preview(
            db,
            dataset,
            code="set_rows_value",
            raw_params={"row_numbers": [2], "column": "Qtd", "value": "1"},
            base_version_id=base,
            actor="t@example.com",
            correlation_id=None,
        )
        prev_b = versioning.create_preview(
            db,
            dataset,
            code="set_rows_value",
            raw_params={"row_numbers": [3], "column": "Qtd", "value": "2"},
            base_version_id=base,
            actor="t@example.com",
            correlation_id=None,
        )
        db.commit()
        ids = (dataset.id, prev_a.id, prev_b.id)

    results: list[str] = []
    barrier = threading.Barrier(2)

    def worker(preview_id: str) -> None:
        barrier.wait()
        try:
            with session_factory() as db:
                dataset_obj = db.get(Dataset, ids[0])
                assert dataset_obj is not None
                versioning.apply_preview(
                    db,
                    dataset_obj,
                    preview_id=preview_id,
                    base_version_id=base,
                    idempotency_key=None,
                    actor="t@example.com",
                    correlation_id=None,
                )
                db.commit()
                results.append("ok")
        except ConflictError:
            results.append("conflito")
        except Exception as exc:  # erro inesperado deve falhar o teste
            results.append(f"erro:{type(exc).__name__}")

    threads = [threading.Thread(target=worker, args=(pid,)) for pid in (ids[1], ids[2])]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert sorted(results) == ["conflito", "ok"], results
    with session_factory() as db:
        versions_count = (
            db.query(DatasetVersion).filter(DatasetVersion.dataset_id == ids[0]).count()
        )
        assert versions_count == 2  # importação + uma aplicação


# ---------- migração 0003 com dados ----------


def test_migration_0003_preserves_existing_rows_and_hash(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dados da 2A (versão 0002) viram versão 1 na 0003 e voltam ao downgrade sem perda."""
    monkeypatch.setenv("ENGIFLOW_DATABASE_URL", database_url)
    get_settings.cache_clear()
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))

    # Tabelas com tipos explícitos (JSON), para inserir e ler com fidelidade.
    datasets = sa.table(
        "datasets",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("source_filename", sa.String),
        sa.column("source_sha256", sa.String),
        sa.column("file_kind", sa.String),
        sa.column("sheet_key", sa.String),
        sa.column("sheet_name", sa.String),
        sa.column("columns", sa.JSON),
        sa.column("row_count", sa.Integer),
        sa.column("mapping", sa.JSON),
        sa.column("warnings", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("current_version_id", sa.String),
    )
    old_rows = sa.table(
        "dataset_rows",
        sa.column("dataset_id", sa.String),
        sa.column("row_number", sa.Integer),
        sa.column("values", sa.JSON),
    )
    new_version_rows = sa.table(
        "dataset_version_rows",
        sa.column("version_id", sa.String),
        sa.column("row_number", sa.Integer),
        sa.column("values", sa.JSON),
    )

    dataset_id = str(uuid.uuid4())
    columns = ["Código", "Qtd"]
    rows: list[list[str | None]] = [["00123", "1"], ["0", None], ["", "7"]]
    try:
        command.upgrade(cfg, "0002_data_studio")
        engine = sa.create_engine(database_url)
        with engine.begin() as conn:
            conn.execute(
                datasets.insert().values(
                    id=dataset_id,
                    name="SYN-mig",
                    source_filename="SYN-mig.csv",
                    source_sha256=hashlib.sha256(b"mig").hexdigest(),
                    file_kind="csv",
                    sheet_key="",
                    sheet_name=None,
                    columns=columns,
                    row_count=3,
                    mapping={"code": "Código"},
                    warnings=[],
                    created_at=dt.datetime.now(dt.UTC),
                )
            )
            conn.execute(
                old_rows.insert(),
                [
                    {"dataset_id": dataset_id, "row_number": i + 2, "values": r}
                    for i, r in enumerate(rows)
                ],
            )
        engine.dispose()

        command.upgrade(cfg, "head")
        engine = sa.create_engine(database_url)
        with engine.connect() as conn:
            version_id: str = conn.execute(
                sa.select(datasets.c.current_version_id).where(datasets.c.id == dataset_id)
            ).scalar_one()
            versions_t = sa.table(
                "dataset_versions",
                sa.column("id", sa.String),
                sa.column("content_sha256", sa.String),
            )
            stored_sha: str = conn.execute(
                sa.select(versions_t.c.content_sha256).where(versions_t.c.id == version_id)
            ).scalar_one()
            migrated = conn.execute(
                sa.select(new_version_rows.c.row_number, new_version_rows.c["values"])
                .where(new_version_rows.c.version_id == version_id)
                .order_by(new_version_rows.c.row_number)
            ).all()
        assert version_id == dataset_id
        # Regressão: ids gerados pela migração cabem na coluna String(36) (PostgreSQL rejeita mais).
        with engine.connect() as conn:
            meta_ids = (
                conn.execute(
                    sa.select(sa.column("id", sa.String)).select_from(
                        sa.table("dataset_metadata_versions", sa.column("id", sa.String))
                    )
                )
                .scalars()
                .all()
            )
        assert meta_ids and all(len(i) <= 36 for i in meta_ids)
        assert stored_sha == content_sha256(columns, rows)
        assert [(n, v) for n, v in migrated] == [(i + 2, r) for i, r in enumerate(rows)]
        engine.dispose()

        command.downgrade(cfg, "0002_data_studio")
        engine = sa.create_engine(database_url)
        with engine.connect() as conn:
            restored = conn.execute(
                sa.select(old_rows.c.row_number, old_rows.c["values"])
                .where(old_rows.c.dataset_id == dataset_id)
                .order_by(old_rows.c.row_number)
            ).all()
        assert [(n, v) for n, v in restored] == [(i + 2, r) for i, r in enumerate(rows)]
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_version_row_model_is_the_only_row_store() -> None:
    assert DatasetVersionRow.__tablename__ == "dataset_version_rows"
    assert "dataset_rows" not in {t.name for t in Base.metadata.sorted_tables}
