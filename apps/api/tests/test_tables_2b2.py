"""2B.2 bloco 7: renomear, excluir logicamente e restaurar tabelas. Dados sintéticos."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings

CSV_A = "SYN-Código;Qtd\n00123;1\n0123;\n".encode()
CSV_B = "SYN-Código;Qtd\nAB1;7\n".encode()


def _import(client: TestClient, filename: str, data: bytes) -> dict[str, Any]:
    resp = client.post("/api/v1/datasets", files={"file": (filename, data, "text/csv")})
    assert resp.status_code == 201, resp.text
    dataset: dict[str, Any] = resp.json()["dataset"]
    return dataset


def _names(client: TestClient, deleted: bool = False) -> list[str]:
    params = {"deleted": "true"} if deleted else {}
    body: list[dict[str, Any]] = client.get("/api/v1/datasets", params=params).json()
    return [d["name"] for d in body]


def test_rename_updates_name_and_rejects_active_duplicate(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    a = _import(logged_client, "SYN-a.csv", CSV_A)
    _import(logged_client, "SYN-b.csv", CSV_B)
    ok = logged_client.patch(f"/api/v1/datasets/{a['id']}", json={"name": "Tabela A"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["name"] == "Tabela A"
    dup = logged_client.patch(f"/api/v1/datasets/{a['id']}", json={"name": "SYN-B"})
    assert dup.status_code == 422
    assert "Já existe" in dup.text
    dup_case = logged_client.patch(f"/api/v1/datasets/{a['id']}", json={"name": "syn-b"})
    assert dup_case.status_code == 422


def test_delete_requires_exact_name_and_hides_table(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    a = _import(logged_client, "SYN-del.csv", CSV_A)
    wrong = logged_client.request(
        "DELETE", f"/api/v1/datasets/{a['id']}", json={"confirm_name": "outro"}
    )
    assert wrong.status_code == 422
    assert "nome exato" in wrong.text
    assert "SYN-del" in _names(logged_client)

    done = logged_client.request(
        "DELETE", f"/api/v1/datasets/{a['id']}", json={"confirm_name": "SYN-del"}
    )
    assert done.status_code == 200, done.text
    assert "SYN-del" not in _names(logged_client)
    assert "SYN-del" in _names(logged_client, deleted=True)


def test_deleted_table_refuses_operations_and_reads(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    a = _import(logged_client, "SYN-off.csv", CSV_A)
    logged_client.request("DELETE", f"/api/v1/datasets/{a['id']}", json={"confirm_name": "SYN-off"})
    assert logged_client.get(f"/api/v1/datasets/{a['id']}").status_code == 422
    assert logged_client.get(f"/api/v1/datasets/{a['id']}/rows").status_code == 422
    preview = logged_client.post(
        f"/api/v1/datasets/{a['id']}/operations/preview",
        json={
            "code": "replace_text",
            "params": {"column": "Qtd", "find": "1", "replace": "2"},
            "base_version_id": a["id"],
        },
    )
    assert preview.status_code == 422


def test_restore_returns_table_to_active_list(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    a = _import(logged_client, "SYN-rst.csv", CSV_A)
    logged_client.request("DELETE", f"/api/v1/datasets/{a['id']}", json={"confirm_name": "SYN-rst"})
    restored = logged_client.post(f"/api/v1/datasets/{a['id']}/restore")
    assert restored.status_code == 200, restored.text
    assert "SYN-rst" in _names(logged_client)
    assert "SYN-rst" not in _names(logged_client, deleted=True)
    assert logged_client.get(f"/api/v1/datasets/{a['id']}").status_code == 200


def test_restore_is_refused_when_an_active_table_has_the_same_name(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    old = _import(logged_client, "SYN-same.csv", CSV_A)
    logged_client.request(
        "DELETE", f"/api/v1/datasets/{old['id']}", json={"confirm_name": "SYN-same"}
    )
    _import(logged_client, "SYN-same.csv", CSV_B)  # outro arquivo, mesmo nome
    restored = logged_client.post(f"/api/v1/datasets/{old['id']}/restore")
    assert restored.status_code == 422
    assert "Já existe uma tabela ativa" in restored.text


def test_reimporting_a_deleted_file_points_to_restore(
    logged_client: TestClient, storage_settings: Settings
) -> None:
    a = _import(logged_client, "SYN-re.csv", CSV_A)
    logged_client.request("DELETE", f"/api/v1/datasets/{a['id']}", json={"confirm_name": "SYN-re"})
    again = logged_client.post(
        "/api/v1/datasets", files={"file": ("SYN-re.csv", CSV_A, "text/csv")}
    )
    assert again.status_code == 422
    assert "Restaure" in again.text
