"""2B.3: integridade e idempotência das tabelas derivadas (regressão). Dados sintéticos.

Cenários:
- resposta perdida após o commit: repetir a chave devolve a mesma tabela, sem duplicar;
- mesma chave com parâmetros diferentes: 409;
- falha antes do commit: nenhuma tabela órfã e nenhuma execução gravada;
- colisão concorrente (dois pedidos com a mesma chave): o perdedor repete o resultado do vencedor.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from engiflow_api.application import crossing as cx
from engiflow_api.core.config import Settings

ESQ = "SYN-Código;SYN-Qtd\n00123;1\n0123;2\nAB1;3\n".encode()
DIR = "SYN-Código;SYN-Descrição\n00123;SYN parafuso\nAB1;SYN arruela\n".encode()


def _import(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (name, data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _body(left: str, right: str, return_columns: list[str] | None = None) -> dict[str, Any]:
    return {
        "left_id": left,
        "right_id": right,
        "left_keys": ["SYN-Código"],
        "right_keys": ["SYN-Código"],
        "return_columns": return_columns if return_columns is not None else ["SYN-Descrição"],
    }


def _count_datasets(client: TestClient) -> int:
    rows: list[dict[str, Any]] = client.get("/api/v1/datasets").json()
    return len(rows)


def test_repeating_key_after_lost_response_returns_same_table(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-idem-esq.csv", ESQ)
    right = _import(logged_client, "SYN-idem-dir.csv", DIR)
    headers = {"Idempotency-Key": "chave-resposta-perdida-1"}
    first = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"]), headers=headers
    )
    assert first.status_code == 201, first.text
    before = _count_datasets(logged_client)

    # Simula cliente que não recebeu a resposta e tenta de novo com a mesma chave.
    second = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"]), headers=headers
    )
    assert second.status_code == 201, second.text
    assert second.json()["dataset_id"] == first.json()["dataset_id"]
    assert second.json()["run_id"] == first.json()["run_id"]
    assert _count_datasets(logged_client) == before  # nada duplicado


def test_same_key_with_different_parameters_is_rejected(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-idem-esq2.csv", ESQ)
    right = _import(logged_client, "SYN-idem-dir2.csv", DIR)
    headers = {"Idempotency-Key": "chave-parametros-diferentes"}
    ok = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"]), headers=headers
    )
    assert ok.status_code == 201, ok.text
    before = _count_datasets(logged_client)

    other = logged_client.post(
        "/api/v1/crossing/lookup/derive",
        json=_body(left["id"], right["id"], return_columns=[]),
        headers=headers,
    )
    assert other.status_code == 409, other.text
    assert _count_datasets(logged_client) == before


def test_key_is_shared_across_operations_but_kind_must_match(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-idem-esq3.csv", ESQ)
    right = _import(logged_client, "SYN-idem-dir3.csv", DIR)
    headers = {"Idempotency-Key": "chave-tipo-diferente"}
    ok = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"]), headers=headers
    )
    assert ok.status_code == 201, ok.text
    join = logged_client.post(
        "/api/v1/crossing/join/derive",
        json={
            "left_id": left["id"],
            "right_id": right["id"],
            "left_keys": ["SYN-Código"],
            "right_keys": ["SYN-Código"],
        },
        headers=headers,
    )
    assert join.status_code == 409, join.text


def test_failure_before_commit_leaves_no_orphan_table(
    logged_client: TestClient, storage_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    left = _import(logged_client, "SYN-idem-esq4.csv", ESQ)
    right = _import(logged_client, "SYN-idem-dir4.csv", DIR)
    before = _count_datasets(logged_client)

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("falha simulada antes do commit")

    monkeypatch.setattr(cx, "record_event", boom)
    with pytest.raises(RuntimeError):
        logged_client.post(
            "/api/v1/crossing/lookup/derive",
            json=_body(left["id"], right["id"]),
            headers={"Idempotency-Key": "chave-falha-antes-commit"},
        )
    monkeypatch.undo()

    assert _count_datasets(logged_client) == before  # sem tabela órfã
    # Repetir com a mesma chave agora cria normalmente (a falha não ficou gravada).
    retry = logged_client.post(
        "/api/v1/crossing/lookup/derive",
        json=_body(left["id"], right["id"]),
        headers={"Idempotency-Key": "chave-falha-antes-commit"},
    )
    assert retry.status_code == 201, retry.text
    assert _count_datasets(logged_client) == before + 1


def test_concurrent_collision_returns_winners_table(
    logged_client: TestClient, storage_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    left = _import(logged_client, "SYN-idem-esq5.csv", ESQ)
    right = _import(logged_client, "SYN-idem-dir5.csv", DIR)
    headers = {"Idempotency-Key": "chave-corrida"}
    winner = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"]), headers=headers
    )
    assert winner.status_code == 201, winner.text
    before = _count_datasets(logged_client)

    # O perdedor não viu a chave ao verificar (a verificação passou antes do commit do vencedor).
    real_replay = cx.replay_derived
    calls = {"n": 0}

    def replay_unseen_first(db: Any, key: Any, kind: Any, params: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_replay(db, key, kind, params)

    monkeypatch.setattr(cx, "replay_derived", replay_unseen_first)
    loser = logged_client.post(
        "/api/v1/crossing/lookup/derive", json=_body(left["id"], right["id"]), headers=headers
    )
    monkeypatch.undo()

    assert loser.status_code == 201, loser.text
    assert loser.json()["dataset_id"] == winner.json()["dataset_id"]
    assert _count_datasets(logged_client) == before
    assert calls["n"] == 2  # a segunda tentativa encontrou a execução gravada pelo vencedor


def test_derived_tables_have_consistent_lineage(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    left = _import(logged_client, "SYN-idem-esq6.csv", ESQ)
    right = _import(logged_client, "SYN-idem-dir6.csv", DIR)
    created = logged_client.post(
        "/api/v1/crossing/lookup/derive",
        json=_body(left["id"], right["id"]),
        headers={"Idempotency-Key": "chave-linhagem"},
    )
    assert created.status_code == 201, created.text
    detail = logged_client.get(f"/api/v1/datasets/{created.json()['dataset_id']}").json()
    assert detail["source_kind"] == "derived"
    assert detail["derived_run_id"] == created.json()["run_id"]
