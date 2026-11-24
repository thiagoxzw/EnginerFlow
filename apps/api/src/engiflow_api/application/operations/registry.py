"""Registro central de capacidades de transformação (2B.1).

Cada capacidade é uma função pura sobre um Snapshot (colunas + linhas). Não acessa banco nem
arquivo. Persistência, prévia e auditoria ficam na camada de versionamento.

Regras comuns:
- Valores: string (texto, zeros preservados), None (desconhecido), "" (vazio). Nunca convertidos.
- Operação que não encontra alvo falha; nunca altera silenciosamente.
- `code_version` sobe quando o comportamento muda: entra no histórico de cada operação.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engiflow_api.domain.errors import DomainError

MAX_SELECTED_ROWS = 10_000


@dataclass
class Snapshot:
    columns: list[str]
    rows: list[list[str | None]]
    row_numbers: list[int]


@dataclass(frozen=True)
class OperationResult:
    snapshot: Snapshot
    rows_affected: int
    cells_changed: int
    warnings: list[str] = field(default_factory=list)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RenameColumnParams(_Strict):
    from_name: str = Field(min_length=1, max_length=255)
    to_name: str = Field(min_length=1, max_length=255)


class ReplaceTextParams(_Strict):
    column: str = Field(min_length=1, max_length=255)
    find: str = Field(min_length=1, max_length=1000)
    replace: str = Field(default="", max_length=1000)
    match_case: bool = True
    whole_cell: bool = False


class SetRowsValueParams(_Strict):
    row_numbers: list[int] = Field(min_length=1, max_length=MAX_SELECTED_ROWS)
    column: str = Field(min_length=1, max_length=255)
    # Obrigatório: string (inclusive "" para vazio) ou null para desconhecido.
    value: str | None = Field(max_length=1000)


def _column_index(snapshot: Snapshot, name: str) -> int:
    try:
        return snapshot.columns.index(name)
    except ValueError as exc:
        raise DomainError(f"Coluna '{name}' não existe nesta versão.") from exc


def _rename_column(snapshot: Snapshot, params: RenameColumnParams) -> OperationResult:
    index = _column_index(snapshot, params.from_name)
    target = params.to_name.strip()
    if not target:
        raise DomainError("Novo nome de coluna não pode ser vazio.")
    others = {c.casefold() for i, c in enumerate(snapshot.columns) if i != index}
    if target.casefold() in others:
        raise DomainError(f"Já existe uma coluna chamada '{target}'.")
    columns = list(snapshot.columns)
    columns[index] = target
    return OperationResult(
        snapshot=Snapshot(columns, snapshot.rows, snapshot.row_numbers),
        rows_affected=0,
        cells_changed=0,
    )


def _replace_text(snapshot: Snapshot, params: ReplaceTextParams) -> OperationResult:
    index = _column_index(snapshot, params.column)
    flags = 0 if params.match_case else re.IGNORECASE
    pattern = re.compile(
        rf"^{re.escape(params.find)}$" if params.whole_cell else re.escape(params.find), flags
    )
    rows: list[list[str | None]] = []
    rows_affected = 0
    cells_changed = 0
    for row in snapshot.rows:
        cell = row[index]
        if cell is None:  # desconhecido não é substituído
            rows.append(row)
            continue
        if params.whole_cell:
            left = cell if params.match_case else cell.casefold()
            needle = params.find if params.match_case else params.find.casefold()
            replaced = params.replace if left == needle else cell
        else:
            replaced = pattern.sub(lambda _m: params.replace, cell)
        if replaced != cell:
            cells_changed += 1
            rows_affected += 1
            new_row = list(row)
            new_row[index] = replaced
            rows.append(new_row)
        else:
            rows.append(row)
    return OperationResult(
        snapshot=Snapshot(list(snapshot.columns), rows, snapshot.row_numbers),
        rows_affected=rows_affected,
        cells_changed=cells_changed,
    )


def _set_rows_value(snapshot: Snapshot, params: SetRowsValueParams) -> OperationResult:
    index = _column_index(snapshot, params.column)
    selected = set(params.row_numbers)
    present = {n for n in snapshot.row_numbers if n in selected}
    missing = sorted(selected - present)
    if missing:
        raise DomainError(
            f"Linhas inexistentes na versão atual: {', '.join(str(n) for n in missing[:10])}."
        )
    rows: list[list[str | None]] = []
    cells_changed = 0
    for number, row in zip(snapshot.row_numbers, snapshot.rows, strict=True):
        if number in selected and row[index] != params.value:
            new_row = list(row)
            new_row[index] = params.value
            cells_changed += 1
            rows.append(new_row)
        else:
            rows.append(row)
    return OperationResult(
        snapshot=Snapshot(list(snapshot.columns), rows, snapshot.row_numbers),
        rows_affected=len(present),
        cells_changed=cells_changed,
    )


@dataclass(frozen=True)
class OperationSpec:
    code: str
    version: int
    description: str
    params_model: type[BaseModel]
    reversible: bool
    apply: Callable[[Snapshot, Any], OperationResult]


OPERATIONS: dict[str, OperationSpec] = {
    "rename_column": OperationSpec(
        code="rename_column",
        version=1,
        description="Renomeia uma coluna. Não altera valores.",
        params_model=RenameColumnParams,
        reversible=True,
        apply=_rename_column,
    ),
    "replace_text": OperationSpec(
        code="replace_text",
        version=1,
        description="Substitui texto em uma coluna. Desconhecidos não são alterados.",
        params_model=ReplaceTextParams,
        reversible=True,
        apply=_replace_text,
    ),
    "set_rows_value": OperationSpec(
        code="set_rows_value",
        version=1,
        description=(
            "Define o valor de uma coluna nas linhas selecionadas (texto, vazio ou desconhecido)."
        ),
        params_model=SetRowsValueParams,
        reversible=True,
        apply=_set_rows_value,
    ),
}


def get_operation(code: str) -> OperationSpec:
    spec = OPERATIONS.get(code)
    if spec is None:
        raise DomainError(f"Operação desconhecida: {code}.")
    return spec


def validate_params(spec: OperationSpec, raw: dict[str, Any]) -> BaseModel:
    try:
        return spec.params_model.model_validate(raw)
    except Exception as exc:  # pydantic.ValidationError -> erro de regra
        raise DomainError(f"Parâmetros inválidos para '{spec.code}': {exc}") from exc
