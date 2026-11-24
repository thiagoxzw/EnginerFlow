"""Lacunas de integridade da 2B.1 (revisão de homologação). Dados SINTÉTICOS (prefixo SYN-).

Cenários já cobertos em test_versioning_2b1.py (não repetidos aqui):
- duas operações simultâneas na mesma versão;
- prévia expirada; reutilização de prévia consumida;
- colisão de nomes na renomeação (unidade e API);
- hash canônico fixado e distinção vazio/desconhecido/zero na serialização.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from engiflow_api.application import versioning
from engiflow_api.application.data_studio import get_dataset
from engiflow_api.application.versioning import load_snapshot
from engiflow_api.core.config import Settings
from engiflow_api.domain.canonical import content_sha256
from engiflow_api.domain.errors import ConflictError
from engiflow_api.infrastructure.models import (
    Dataset,
    DatasetOperation,
    DatasetPreview,
    DatasetVersion,
    DatasetVersionRow,
)
from tests.test_versioning_2b1 import (  # reuso dos helpers e da fixture, sem duplicar
    _apply,
    _current,
    _import,
    _preview,
    _rows,
    _versions,
)

# ---------- 2. mesma Idempotency-Key com parâmetros diferentes ----------


def test_same_idempotency_key_with_different_params_is_conflict(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    first = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "1"},
        base,
    )
    applied = _apply(logged_client, ds["id"], first["preview_id"], base, key="K-1")
    assert applied.status_code == 201
    v2 = applied.json()["current_version_id"]
    second = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [3], "column": "Qtd", "value": "2"},
        v2,
    )
    resp = _apply(logged_client, ds["id"], second["preview_id"], v2, key="K-1")
    assert resp.status_code == 409
    assert len(_versions(logged_client, ds["id"])) == 2  # nenhuma versão extra


# ---------- 5. prévia após undo e redo ----------


def test_preview_from_undone_state_is_refused_after_redo_changes_base(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    v1 = _current(logged_client, ds["id"])
    p1 = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "5"},
        v1,
    )
    v2 = _apply(logged_client, ds["id"], p1["preview_id"], v1).json()["current_version_id"]
    stale = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [3], "column": "Qtd", "value": "6"},
        v2,
    )
    logged_client.post(f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": v2})
    # prévia foi gerada em v2; a tabela agora está em v1: deve ser recusada
    assert _apply(logged_client, ds["id"], stale["preview_id"], v2).status_code == 409


def test_preview_generated_in_restored_state_is_refused_after_redo_and_hash_is_deterministic(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    """Prévia gerada em v1 (após undo) deixa de valer quando o redo leva a tabela de volta a v2."""
    ds = _import(logged_client)
    v1 = _current(logged_client, ds["id"])
    p1 = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "5"},
        v1,
    )
    v2 = _apply(logged_client, ds["id"], p1["preview_id"], v1).json()["current_version_id"]
    v2_hash = next(v["content_sha256"] for v in _versions(logged_client, ds["id"]) if v["id"] == v2)

    assert (
        logged_client.post(
            f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": v2}
        ).status_code
        == 200
    )
    assert _current(logged_client, ds["id"]) == v1
    again = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "5"},
        v1,
    )
    assert again["after_content_sha256"] == v2_hash  # mesmo resultado lógico, mesmo hash

    redo = logged_client.post(f"/api/v1/datasets/{ds['id']}/redo", json={"base_version_id": v1})
    assert redo.json()["current_version_id"] == v2
    # A tabela voltou a v2: a prévia feita em v1 não pode ser aplicada.
    assert _apply(logged_client, ds["id"], again["preview_id"], v1).status_code == 409


# ---------- 6. nova operação após múltiplos undos ----------


def test_new_operation_after_multiple_undos_discards_the_redo_branch(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    v1 = _current(logged_client, ds["id"])
    pa = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "A"},
        v1,
    )
    va = _apply(logged_client, ds["id"], pa["preview_id"], v1).json()["current_version_id"]
    pb = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "B"},
        va,
    )
    vb = _apply(logged_client, ds["id"], pb["preview_id"], va).json()["current_version_id"]
    assert (
        logged_client.post(
            f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": vb}
        ).status_code
        == 200
    )
    assert (
        logged_client.post(
            f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": va}
        ).status_code
        == 200
    )
    assert _current(logged_client, ds["id"]) == v1

    pc = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "C"},
        v1,
    )
    vc = _apply(logged_client, ds["id"], pc["preview_id"], v1).json()
    assert vc["operation"]["seq"] == 3
    ops = logged_client.get(f"/api/v1/datasets/{ds['id']}/operations").json()
    assert [(o["seq"], o["status"]) for o in ops] == [(1, "undone"), (2, "undone"), (3, "applied")]
    # Refazer não ressuscita o ramo descartado: nada a refazer a partir de vc.
    redo = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/redo", json={"base_version_id": vc["current_version_id"]}
    )
    assert redo.status_code == 422
    assert _rows(logged_client, ds["id"])[0][2] == "C"


# ---------- 7. mapeamento através de renomeações sucessivas ----------


def test_mapping_survives_successive_renames_and_undo_steps_back(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    ds = _import(logged_client)
    logged_client.put(
        f"/api/v1/datasets/{ds['id']}/mapping", json={"mapping": {"code": "SYN-Código"}}
    )
    v = _current(logged_client, ds["id"])
    p1 = _preview(
        logged_client, ds["id"], "rename_column", {"from_name": "SYN-Código", "to_name": "Cod1"}, v
    )
    v = _apply(logged_client, ds["id"], p1["preview_id"], v).json()["current_version_id"]
    p2 = _preview(
        logged_client, ds["id"], "rename_column", {"from_name": "Cod1", "to_name": "Cod2"}, v
    )
    v2 = _apply(logged_client, ds["id"], p2["preview_id"], v).json()["current_version_id"]
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["mapping"] == {"code": "Cod2"}
    assert "Cod2" in detail["columns"]

    back1 = logged_client.post(
        f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": v2}
    ).json()["current_version_id"]
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["mapping"] == {"code": "Cod1"}
    logged_client.post(f"/api/v1/datasets/{ds['id']}/undo", json={"base_version_id": back1})
    detail = logged_client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert detail["mapping"] == {"code": "SYN-Código"}


# ---------- 8. rollback completo quando a transformação falha ----------


def test_failure_mid_transformation_rolls_back_version_operation_and_preview(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    logged_client: TestClient,
    storage_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    prev = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "9"},
        base,
    )

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("falha simulada após gravar a versão")

    monkeypatch.setattr(versioning, "_move_pointer", boom)
    with session_factory() as db:
        dataset = get_dataset(db, ds["id"])
        with pytest.raises(RuntimeError):
            versioning.apply_preview(
                db,
                dataset,
                preview_id=prev["preview_id"],
                base_version_id=base,
                idempotency_key=None,
                actor="t@example.com",
                correlation_id=None,
            )
        db.rollback()  # o que a camada HTTP faz ao propagar a exceção

    with session_factory() as db:
        assert db.query(DatasetVersion).filter(DatasetVersion.dataset_id == ds["id"]).count() == 1
        assert (
            db.query(DatasetOperation).filter(DatasetOperation.dataset_id == ds["id"]).count() == 0
        )
        preview = db.get(DatasetPreview, prev["preview_id"])
        assert preview is not None and preview.consumed_at is None  # prévia continua utilizável
        current = db.get(Dataset, ds["id"])
        assert current is not None and current.current_version_id == base
        orphan_rows = (
            db.query(DatasetVersionRow).filter(DatasetVersionRow.version_id != base).count()
        )
        assert orphan_rows == 0
    monkeypatch.undo()
    assert _rows(logged_client, ds["id"])[0][2] == "1"  # valor original preservado


# ---------- 9. zeros à esquerda, vazio, desconhecido e zero através das operações ----------


def test_empty_unknown_zero_and_leading_zeros_survive_operations(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    data = "SYN-Código;SYN-Qtd\n00123;\n0;0\nAB1;7\n".encode()
    ds = _import(logged_client, data)
    v1 = _current(logged_client, ds["id"])
    rows = _rows(logged_client, ds["id"])
    assert rows[0] == ["00123", ""]  # vazio preservado
    assert rows[1] == ["0", "0"]  # zero preservado como texto
    p = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [4], "column": "SYN-Qtd", "value": None},
        v1,
    )
    _apply(logged_client, ds["id"], p["preview_id"], v1)
    rows = _rows(logged_client, ds["id"])
    assert rows[0] == ["00123", ""]  # vazio continua vazio
    assert rows[1] == ["0", "0"]  # zero continua zero
    assert rows[2] == ["AB1", None]  # desconhecido aplicado como desconhecido, não como vazio


# ---------- 10. imutabilidade das versões anteriores ----------


def test_previous_versions_are_not_modified_by_later_operations(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    logged_client: TestClient,
    storage_settings: Settings,
) -> None:
    ds = _import(logged_client)
    v1 = _current(logged_client, ds["id"])
    with session_factory() as db:
        before = [
            (r.row_number, list(r.values))
            for r in db.scalars(
                select(DatasetVersionRow)
                .where(DatasetVersionRow.version_id == v1)
                .order_by(DatasetVersionRow.row_number)
            ).all()
        ]
        sha_before = db.get(DatasetVersion, v1).content_sha256
    p = _preview(
        logged_client,
        ds["id"],
        "replace_text",
        {"column": "SYN-Descrição", "find": "SYN", "replace": "X"},
        v1,
    )
    _apply(logged_client, ds["id"], p["preview_id"], v1)
    with session_factory() as db:
        after = [
            (r.row_number, list(r.values))
            for r in db.scalars(
                select(DatasetVersionRow)
                .where(DatasetVersionRow.version_id == v1)
                .order_by(DatasetVersionRow.row_number)
            ).all()
        ]
        assert after == before
        assert db.get(DatasetVersion, v1).content_sha256 == sha_before


# ---------- 11. integridade do hash canônico armazenado ----------


def test_stored_hash_of_every_version_matches_its_rows(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    logged_client: TestClient,
    storage_settings: Settings,
) -> None:
    ds = _import(logged_client)
    v = _current(logged_client, ds["id"])
    p = _preview(
        logged_client,
        ds["id"],
        "replace_text",
        {"column": "SYN-Descrição", "find": "SYN", "replace": "Z"},
        v,
    )
    _apply(logged_client, ds["id"], p["preview_id"], v)
    with session_factory() as db:
        for version in db.scalars(
            select(DatasetVersion).where(DatasetVersion.dataset_id == ds["id"])
        ).all():
            rows = [
                list(r.values)
                for r in db.scalars(
                    select(DatasetVersionRow)
                    .where(DatasetVersionRow.version_id == version.id)
                    .order_by(DatasetVersionRow.row_number)
                ).all()
            ]
            snap = load_snapshot(db, version.id)
            assert version.content_sha256 == content_sha256(snap.columns, rows)
            assert version.row_count == len(rows)


def test_version_number_collision_is_reported_as_conflict_not_integrity_error(
    session_factory: sessionmaker,  # type: ignore[type-arg]
    logged_client: TestClient,
    storage_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duas aplicações concorrentes calculam o mesmo número de versão.

    Defeito reproduzido: a violação de unicidade estourava como IntegrityError (HTTP 500),
    fora do bloco que converte em ConflictError (409). Forçamos a colisão de forma determinística.
    """
    ds = _import(logged_client)
    base = _current(logged_client, ds["id"])
    p1 = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [2], "column": "Qtd", "value": "1"},
        base,
    )
    p2 = _preview(
        logged_client,
        ds["id"],
        "set_rows_value",
        {"row_numbers": [3], "column": "Qtd", "value": "2"},
        base,
    )
    # Primeira aplicação grava a versão 2 normalmente.
    assert _apply(logged_client, ds["id"], p1["preview_id"], base).status_code == 201
    # Segunda aplicação (base antiga) calcula o número 2 de novo: colisão com a versão já gravada.
    monkeypatch.setattr(versioning, "_next_number", lambda db, dataset_id: 2)
    with session_factory() as db:
        dataset = get_dataset(db, ds["id"])
        dataset.current_version_id = base  # simula a leitura concorrente feita com a base antiga
        with pytest.raises(ConflictError):
            versioning.apply_preview(
                db,
                dataset,
                preview_id=p2["preview_id"],
                base_version_id=base,
                idempotency_key=None,
                actor="t@example.com",
                correlation_id=None,
            )
        db.rollback()
