"""Numeração de revisões do BOM sob concorrência.

- test_trava_compila_com_for_update: roda em qualquer banco. Garante que a consulta de trava
  usa FOR UPDATE no PostgreSQL (o SQLite ignora a instrução).
- test_segunda_transacao_espera_o_commit_da_primeira: exige PostgreSQL real. Defina
  ENGIFLOW_TEST_DATABASE_URL para rodar; sem ela o teste é pulado. Prova o bloqueio de fato:
  uma segunda transação para a mesma estrutura só continua após o commit da primeira.
"""

from __future__ import annotations

import os
import threading
import time

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from engiflow_api.application.bom import _next_number, lock_structure_statement
from engiflow_api.infrastructure import bom_models as m


def test_trava_compila_com_for_update() -> None:
    sql = str(lock_structure_statement("abc").compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql


@pytest.mark.skipif(
    not os.environ.get("ENGIFLOW_TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="Defina ENGIFLOW_TEST_DATABASE_URL com PostgreSQL para testar o bloqueio real.",
)
def test_segunda_transacao_espera_o_commit_da_primeira(session_factory: sessionmaker) -> None:  # type: ignore[type-arg]
    factory = session_factory
    with factory() as setup:
        structure = m.BomStructure(name="SYN-trava-concorrencia", description="")
        setup.add(structure)
        setup.commit()
        sid = structure.id

    first = factory()
    assert _next_number(first, sid) == 1  # mantém a trava até o commit

    result: dict[str, object] = {}

    def second() -> None:
        with factory() as other:
            result["number"] = _next_number(other, sid)
            result["at"] = time.monotonic()

    worker = threading.Thread(target=second)
    worker.start()
    worker.join(timeout=0.8)
    assert worker.is_alive(), "a segunda transação deveria estar bloqueada pela primeira"

    committed_at = time.monotonic()
    first.commit()
    first.close()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert result["at"] >= committed_at  # só retornou após o commit
    assert result["number"] == 1  # sem revisões criadas, o próximo número ainda é 1
