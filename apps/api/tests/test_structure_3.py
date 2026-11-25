"""Fase 3: operações estruturais (linhas e colunas) como funções puras sobre o snapshot.

Dados sintéticos apenas. Histórico, desfazer e versionamento são cobertos pelas operações
existentes da camada de versionamento (mesmo caminho de prévia e aplicação).
"""

from __future__ import annotations

import pytest

from engiflow_api.application.operations.registry import (
    Snapshot,
    get_operation,
    validate_params,
)
from engiflow_api.domain.errors import DomainError


def _snap() -> Snapshot:
    return Snapshot(
        columns=["Código", "Descrição", "Qtd"],
        rows=[["00123", "parafuso M8", "1"], ["0123", "Parafuso M8", None], ["AB1", "", "7"]],
        row_numbers=[2, 3, 4],
        mapping={"code": "Código", "quantity": "Qtd"},
    )


def _run(code: str, raw: dict[str, object], snapshot: Snapshot | None = None):  # type: ignore[no-untyped-def]
    spec = get_operation(code)
    params = validate_params(spec, raw)
    return spec.apply(snapshot or _snap(), params)


# --- linhas ----------------------------------------------------------------------------


def test_insert_rows_after_a_row_creates_empty_rows_with_new_numbers() -> None:
    result = _run("insert_rows", {"after_row_number": 3, "count": 2})
    assert result.snapshot.row_numbers == [2, 3, 5, 6, 4]
    assert result.snapshot.rows[2] == ["", "", ""]
    assert result.snapshot.rows[3] == ["", "", ""]
    assert result.rows_affected == 2
    assert result.cells_changed == 6


def test_insert_rows_at_top_and_keeps_existing_values() -> None:
    result = _run("insert_rows", {"after_row_number": 0, "count": 1})
    assert result.snapshot.row_numbers == [5, 2, 3, 4]
    assert result.snapshot.rows[1] == ["00123", "parafuso M8", "1"]


def test_insert_rows_rejects_unknown_reference_row() -> None:
    with pytest.raises(DomainError, match="não existe"):
        _run("insert_rows", {"after_row_number": 99, "count": 1})


def test_duplicate_rows_places_copy_below_and_keeps_unknown_values() -> None:
    result = _run("duplicate_rows", {"row_numbers": [3]})
    assert result.snapshot.row_numbers == [2, 3, 5, 4]
    assert result.snapshot.rows[1] == result.snapshot.rows[2]
    # Desconhecido (None) continua desconhecido na cópia, não vira vazio.
    assert result.snapshot.rows[2][2] is None
    assert result.rows_affected == 1


def test_duplicate_rows_rejects_missing_rows() -> None:
    with pytest.raises(DomainError, match="inexistentes"):
        _run("duplicate_rows", {"row_numbers": [42]})


# --- colunas ---------------------------------------------------------------------------


def test_insert_column_after_a_column_keeps_mapping_and_fills_empty() -> None:
    result = _run("insert_column", {"after_column": "Código", "name": "Lote"})
    assert result.snapshot.columns == ["Código", "Lote", "Descrição", "Qtd"]
    assert result.snapshot.rows[0] == ["00123", "", "parafuso M8", "1"]
    assert result.snapshot.mapping == {"code": "Código", "quantity": "Qtd"}


def test_insert_column_at_end_when_no_reference() -> None:
    result = _run("insert_column", {"name": "Obs"})
    assert result.snapshot.columns[-1] == "Obs"
    assert result.snapshot.rows[2][-1] == ""


def test_insert_column_rejects_duplicate_name_ignoring_case() -> None:
    with pytest.raises(DomainError, match="Já existe"):
        _run("insert_column", {"name": "qtd"})


def test_duplicate_column_copies_values_and_keeps_unknown() -> None:
    result = _run("duplicate_column", {"column": "Qtd", "name": "Qtd (cópia)"})
    assert result.snapshot.columns == ["Código", "Descrição", "Qtd", "Qtd (cópia)"]
    assert result.snapshot.rows[1][2] is None
    assert result.snapshot.rows[1][3] is None
    assert result.snapshot.rows[0][3] == "1"


def test_delete_columns_removes_mapping_and_warns() -> None:
    result = _run("delete_columns", {"columns": ["Qtd"]})
    assert result.snapshot.columns == ["Código", "Descrição"]
    assert result.snapshot.mapping == {"code": "Código"}
    assert any("quantity" in w or "Campo 'quantity'" in w for w in result.warnings)


def test_delete_columns_refuses_to_delete_everything() -> None:
    with pytest.raises(DomainError, match="todas as colunas"):
        _run("delete_columns", {"columns": ["Código", "Descrição", "Qtd"]})


def test_delete_columns_rejects_repeated_and_unknown_names() -> None:
    with pytest.raises(DomainError, match="repetidas"):
        _run("delete_columns", {"columns": ["Qtd", "Qtd"]})
    with pytest.raises(DomainError, match="não existe"):
        _run("delete_columns", {"columns": ["Inexistente"]})


def test_preserves_zero_and_empty_distinctions_after_structure_changes() -> None:
    # "0", "" e None continuam distintos depois de inserir e duplicar.
    snap = Snapshot(
        columns=["A"],
        rows=[["0"], [""], [None]],
        row_numbers=[1, 2, 3],
    )
    result = _run("duplicate_column", {"column": "A", "name": "B"}, snap)
    assert [row[1] for row in result.snapshot.rows] == ["0", "", None]
