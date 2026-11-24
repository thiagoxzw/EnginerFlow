"""Testes unitários sem banco: segurança, auditoria e configuração."""

import pytest

from engiflow_api.application.audit import redact
from engiflow_api.application.auth import create_user
from engiflow_api.application.security import hash_password, hash_token, verify_password
from engiflow_api.infrastructure.db import build_engine, build_session_factory
from engiflow_api.infrastructure.models import Base


def test_password_hash_roundtrip_and_rejects_wrong() -> None:
    h = hash_password("uma-senha-longa-123")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "uma-senha-longa-123")
    assert not verify_password(h, "outra-senha-qualquer")
    assert not verify_password("hash-invalido", "qualquer")


def test_token_hash_is_stable_and_not_the_token() -> None:
    token = "token-exemplo"
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token
    assert len(hash_token(token)) == 64


def test_redact_masks_sensitive_keys_recursively() -> None:
    data = {
        "senha": "123",
        "api_key": "abc",
        "nested": {"Authorization": "Bearer x", "ok": "fine"},
        "list": [{"token": "t"}],
        "arquivo": "linha",
    }
    out = redact(data)
    assert out["senha"] == "***"
    assert out["api_key"] == "***"
    assert out["nested"]["Authorization"] == "***"
    assert out["nested"]["ok"] == "fine"
    assert out["list"][0]["token"] == "***"


def test_redact_truncates_long_strings() -> None:
    out = redact({"conteudo": "x" * 1000})
    assert out["conteudo"].endswith("...[truncado]")
    assert len(out["conteudo"]) < 600


def test_create_user_enforces_single_user_and_min_password(tmp_path: object) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    url = f"sqlite:///{(tmp_path / 'u.db').as_posix()}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with factory() as db:
        with pytest.raises(ValueError, match="pelo menos 12"):
            create_user(db, email="a@b.c", display_name="A", password="curta")
        create_user(db, email="a@b.c", display_name="A", password="senha-com-doze-ou-mais")
        db.commit()
    with factory() as db, pytest.raises(ValueError, match="uso individual"):
        create_user(db, email="x@y.z", display_name="X", password="outra-senha-longa-1")
    engine.dispose()
