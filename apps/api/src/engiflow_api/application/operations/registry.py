"""Registro central de capacidades de transformação (2B.1 e 2B.2).

Cada capacidade é uma função pura sobre um Snapshot (colunas, linhas, mapeamento, cabeçalho).
Não acessa banco nem arquivo. Persistência, prévia e auditoria ficam na camada de versionamento.

Regras comuns:
- Valores: string (texto, zeros preservados), None (desconhecido), "" (vazio). Nunca convertidos.
- Operação que não encontra alvo falha; nunca altera silenciosamente.
- `touches_data=False`: operação só de metadados. Não copia linhas; cria só versão de metadados.
- `code_version` sobe quando o comportamento muda: entra no histórico de cada operação.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.query import MAX_FILTERS, FilterIn, RowMatcher, TableQuery
from engiflow_api.domain.tabular import CANONICAL_FIELDS

MAX_SELECTED_ROWS = 10_000


@dataclass
class Snapshot:
    columns: list[str]
    rows: list[list[str | None]]
    row_numbers: list[int]
    mapping: dict[str, str] = field(default_factory=dict)
    header_row: int | None = None
    # Referência ao template que originou o mapeamento (None quando mapeado manualmente).
    template_id: str | None = None
    template_definition_version: int | None = None


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


MAX_REPLACE_COLUMNS = 20


class ReplaceTextParams(_Strict):
    # `column` é o formato da versão 1 (uma coluna). `columns` é o formato em lote.
    column: str | None = Field(default=None, min_length=1, max_length=255)
    columns: list[str] = Field(default_factory=list, max_length=MAX_REPLACE_COLUMNS)
    find: str = Field(min_length=1, max_length=1000)
    replace: str = Field(default="", max_length=1000)
    match_case: bool = True
    whole_cell: bool = False
    # Só linhas que casam com TODOS os filtros são alteradas. Sem filtro: todas as linhas.
    filters: list[FilterIn] = Field(default_factory=list, max_length=MAX_FILTERS)

    @model_validator(mode="after")
    def _one_of_column_or_columns(self) -> ReplaceTextParams:
        if self.column and not self.columns:
            self.columns = [self.column]
        if not self.columns:
            raise ValueError("Informe ao menos uma coluna.")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("Colunas repetidas na substituição.")
        return self


class SetRowsValueParams(_Strict):
    row_numbers: list[int] = Field(min_length=1, max_length=MAX_SELECTED_ROWS)
    column: str = Field(min_length=1, max_length=255)
    # Obrigatório: string (inclusive "" para vazio) ou null para desconhecido.
    value: str | None = Field(max_length=1000)


class SetMappingParams(_Strict):
    # campo canônico -> nome da coluna. Campos ausentes ficam sem mapeamento.
    mapping: dict[str, str] = Field(default_factory=dict)


def _column_index(snapshot: Snapshot, name: str) -> int:
    try:
        return snapshot.columns.index(name)
    except ValueError as exc:
        raise DomainError(f"Coluna '{name}' não existe nesta versão.") from exc


def _with(snapshot: Snapshot, **changes: Any) -> Snapshot:
    """Cópia do snapshot com campos alterados (rasa para linhas que não mudaram)."""
    base: dict[str, Any] = {
        "columns": list(snapshot.columns),
        "rows": snapshot.rows,
        "row_numbers": snapshot.row_numbers,
        "mapping": dict(snapshot.mapping),
        "header_row": snapshot.header_row,
    }
    base.update(changes)
    return Snapshot(**base)


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
    mapping = {
        field_name: (target if column == params.from_name else column)
        for field_name, column in snapshot.mapping.items()
    }
    return OperationResult(
        snapshot=_with(snapshot, columns=columns, mapping=mapping),
        rows_affected=0,
        cells_changed=0,
    )


def _replace_text(snapshot: Snapshot, params: ReplaceTextParams) -> OperationResult:
    """Substitui texto nas colunas indicadas, nas linhas que casam com os filtros.

    Desconhecido (None) nunca é alterado. Vazio e zero são texto comum. Contagens:
    `rows_affected` = linhas com ao menos uma célula alterada; `cells_changed` = células.
    """
    indexes: list[int] = []
    for name in params.columns:
        index = _column_index(snapshot, name)
        indexes.append(index)
    matcher = RowMatcher(list(snapshot.columns), TableQuery(filters=list(params.filters)))
    flags = 0 if params.match_case else re.IGNORECASE
    pattern = re.compile(re.escape(params.find), flags)

    def replaced_cell(cell: str) -> str:
        if params.whole_cell:
            return params.replace if pattern.fullmatch(cell) else cell
        return pattern.sub(lambda _m: params.replace, cell)

    rows: list[list[str | None]] = []
    rows_affected = 0
    cells_changed = 0
    for row in snapshot.rows:
        if not matcher.matches(row):
            rows.append(row)
            continue
        new_row: list[str | None] | None = None
        for index in indexes:
            cell = row[index]
            if cell is None:  # desconhecido não é substituído
                continue
            value = replaced_cell(cell)
            if value != cell:
                if new_row is None:
                    new_row = list(row)
                new_row[index] = value
                cells_changed += 1
        if new_row is not None:
            rows_affected += 1
            rows.append(new_row)
        else:
            rows.append(row)
    return OperationResult(
        snapshot=_with(snapshot, rows=rows),
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
        snapshot=_with(snapshot, rows=rows),
        rows_affected=len(present),
        cells_changed=cells_changed,
    )


MAX_CELLS_PER_OPERATION = 5_000


class CellAssignment(_Strict):
    row_number: int = Field(ge=1)
    column: str = Field(min_length=1, max_length=255)
    value: str | None = None


class SetCellsParams(_Strict):
    """Várias células numa operação só (colagem). Uma entrada no histórico, desfeita de uma vez."""

    cells: list[CellAssignment] = Field(min_length=1, max_length=MAX_CELLS_PER_OPERATION)


def _set_cells(snapshot: Snapshot, params: SetCellsParams) -> OperationResult:
    indexes = {name: _column_index(snapshot, name) for name in {c.column for c in params.cells}}
    by_row: dict[int, dict[int, str | None]] = {}
    for cell in params.cells:
        by_row.setdefault(cell.row_number, {})[indexes[cell.column]] = cell.value
    present = set(snapshot.row_numbers)
    missing = sorted(set(by_row) - present)
    if missing:
        raise DomainError(
            f"Linhas inexistentes na versão atual: {', '.join(str(n) for n in missing[:10])}."
        )
    rows: list[list[str | None]] = []
    cells_changed = 0
    affected: set[int] = set()
    for number, row in zip(snapshot.row_numbers, snapshot.rows, strict=True):
        changes = by_row.get(number)
        if not changes:
            rows.append(row)
            continue
        new_row = list(row)
        changed = False
        for index, value in changes.items():
            if new_row[index] != value:
                new_row[index] = value
                cells_changed += 1
                changed = True
        if changed:
            affected.add(number)
            rows.append(new_row)
        else:
            rows.append(row)
    return OperationResult(
        snapshot=_with(snapshot, rows=rows),
        rows_affected=len(affected),
        cells_changed=cells_changed,
    )


class ApplyTemplateParams(_Strict):
    template_id: str = Field(min_length=1, max_length=36)
    definition_version: int = Field(ge=1)
    # Mapeamento copiado do template no momento da prévia (a aplicação usa exatamente isto).
    mapping: dict[str, str] = Field(default_factory=dict)
    # Colunas do modelo ausentes na tabela só são ignoradas com confirmação explícita.
    allow_missing: bool = False


def _apply_mapping_template(snapshot: Snapshot, params: ApplyTemplateParams) -> OperationResult:
    unknown_fields = sorted(set(params.mapping) - set(CANONICAL_FIELDS))
    if unknown_fields:
        raise DomainError(f"Campos desconhecidos no modelo: {', '.join(unknown_fields)}.")
    present = {f: c for f, c in params.mapping.items() if c in snapshot.columns}
    absent = {f: c for f, c in params.mapping.items() if c not in snapshot.columns}
    if absent and not params.allow_missing:
        names = ", ".join(sorted(set(absent.values())))
        raise DomainError(
            f"Colunas do modelo não existem nesta tabela: {names}. "
            "Confirme para aplicar mesmo assim (campos ausentes ficam sem mapeamento)."
        )
    warnings = [
        f"Campo '{f}' sem coluna correspondente ('{c}'): ignorado." for f, c in absent.items()
    ]
    return OperationResult(
        snapshot=_with(
            snapshot,
            mapping=present,
            template_id=params.template_id,
            template_definition_version=params.definition_version,
        ),
        rows_affected=0,
        cells_changed=0,
        warnings=warnings,
    )


class SetHeaderParams(_Strict):
    header_row: int = Field(ge=1, le=1_000_000)


def _set_header_row(snapshot: Snapshot, params: SetHeaderParams) -> OperationResult:
    """`snapshot` já foi reconstruído do arquivo original com o cabeçalho escolhido.

    O mapeamento anterior é mantido só para colunas que ainda existem; o resto vira aviso.
    """
    mapping = {f: c for f, c in snapshot.mapping.items() if c in snapshot.columns}
    warnings = [
        f"Campo '{f}' sem coluna após trocar o cabeçalho ('{c}'): mapeamento removido."
        for f, c in snapshot.mapping.items()
        if c not in snapshot.columns
    ]
    return OperationResult(
        snapshot=_with(snapshot, mapping=mapping, header_row=params.header_row),
        rows_affected=len(snapshot.rows),
        cells_changed=0,
        warnings=warnings,
    )


class DeleteRowsParams(_Strict):
    row_numbers: list[int] = Field(min_length=1, max_length=MAX_SELECTED_ROWS)


def _delete_rows(snapshot: Snapshot, params: DeleteRowsParams) -> OperationResult:
    """Exclusão lógica: a linha sai desta versão, mas continua nas versões anteriores.

    Os números de linha das demais são preservados (não são renumerados).
    """
    selected = set(params.row_numbers)
    present = {n for n in snapshot.row_numbers if n in selected}
    missing = sorted(selected - present)
    if missing:
        raise DomainError(
            f"Linhas inexistentes na versão atual: {', '.join(str(n) for n in missing[:10])}."
        )
    rows: list[list[str | None]] = []
    numbers: list[int] = []
    for number, row in zip(snapshot.row_numbers, snapshot.rows, strict=True):
        if number not in selected:
            rows.append(row)
            numbers.append(number)
    return OperationResult(
        snapshot=_with(snapshot, rows=rows, row_numbers=numbers),
        rows_affected=len(present),
        cells_changed=0,
    )


def _set_mapping(snapshot: Snapshot, params: SetMappingParams) -> OperationResult:
    unknown_fields = sorted(set(params.mapping) - set(CANONICAL_FIELDS))
    if unknown_fields:
        raise DomainError(f"Campos desconhecidos no mapeamento: {', '.join(unknown_fields)}.")
    missing = sorted({c for c in params.mapping.values() if c not in snapshot.columns})
    if missing:
        raise DomainError(f"Colunas inexistentes na tabela: {', '.join(missing)}.")
    return OperationResult(
        snapshot=_with(snapshot, mapping=dict(params.mapping)),
        rows_affected=0,
        cells_changed=0,
    )


MAX_NEW_ROWS = 1_000
MAX_DELETED_COLUMNS = 100


class InsertRowsParams(_Strict):
    # 0 = inserir no início. Novas linhas ficam vazias ("" em cada célula).
    after_row_number: int = Field(ge=0)
    count: int = Field(ge=1, le=MAX_NEW_ROWS)


def _consecutive(count: int, base: int) -> list[int]:
    """Números consecutivos a partir de `base`, na ordem exibida.

    A versão guarda só o número de cada linha, e a leitura ordena por ele. Por isso, ao inserir
    ou duplicar, as linhas são renumeradas na ordem exibida, como em uma planilha.
    """
    return list(range(base, base + count))


def _base_number(snapshot: Snapshot) -> int:
    return min(snapshot.row_numbers, default=2)


def _insert_rows(snapshot: Snapshot, params: InsertRowsParams) -> OperationResult:
    """Insere linhas vazias após uma linha existente. Números novos, sem renumerar as demais."""
    if params.after_row_number and params.after_row_number not in snapshot.row_numbers:
        raise DomainError(f"Linha {params.after_row_number} não existe nesta versão.")
    width = len(snapshot.columns)
    fresh_rows: list[list[str | None]] = [[""] * width for _ in range(params.count)]
    rows: list[list[str | None]] = []
    if params.after_row_number == 0:
        rows.extend(fresh_rows)
    for number, row in zip(snapshot.row_numbers, snapshot.rows, strict=True):
        rows.append(row)
        if number == params.after_row_number:
            rows.extend(fresh_rows)
    numbers = _consecutive(len(rows), _base_number(snapshot))
    return OperationResult(
        snapshot=_with(snapshot, rows=rows, row_numbers=numbers),
        rows_affected=params.count,
        cells_changed=params.count * width,
    )


class DuplicateRowsParams(_Strict):
    row_numbers: list[int] = Field(min_length=1, max_length=MAX_SELECTED_ROWS)


def _duplicate_rows(snapshot: Snapshot, params: DuplicateRowsParams) -> OperationResult:
    """Cada linha selecionada ganha uma cópia logo abaixo, com número novo."""
    selected = set(params.row_numbers)
    present = {n for n in snapshot.row_numbers if n in selected}
    missing = sorted(selected - present)
    if missing:
        raise DomainError(
            f"Linhas inexistentes na versão atual: {', '.join(str(n) for n in missing[:10])}."
        )
    rows: list[list[str | None]] = []
    for number, row in zip(snapshot.row_numbers, snapshot.rows, strict=True):
        rows.append(row)
        if number in selected:
            rows.append(list(row))
    numbers = _consecutive(len(rows), _base_number(snapshot))
    return OperationResult(
        snapshot=_with(snapshot, rows=rows, row_numbers=numbers),
        rows_affected=len(present),
        cells_changed=len(present) * len(snapshot.columns),
    )


class InsertColumnParams(_Strict):
    # None = inserir no fim. Nova coluna começa vazia ("") em todas as linhas.
    after_column: str | None = Field(default=None, min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)


def _check_new_column_name(snapshot: Snapshot, name: str) -> str:
    target = name.strip()
    if not target:
        raise DomainError("Nome da coluna não pode ser vazio.")
    if target.casefold() in {c.casefold() for c in snapshot.columns}:
        raise DomainError(f"Já existe uma coluna chamada '{target}'.")
    return target


def _insert_column(snapshot: Snapshot, params: InsertColumnParams) -> OperationResult:
    target = _check_new_column_name(snapshot, params.name)
    position = (
        len(snapshot.columns)
        if params.after_column is None
        else _column_index(snapshot, params.after_column) + 1
    )
    columns = [*snapshot.columns[:position], target, *snapshot.columns[position:]]
    rows = [[*row[:position], "", *row[position:]] for row in snapshot.rows]
    return OperationResult(
        snapshot=_with(snapshot, columns=columns, rows=rows),
        rows_affected=0,
        cells_changed=len(rows),
    )


class DuplicateColumnParams(_Strict):
    column: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)


def _duplicate_column(snapshot: Snapshot, params: DuplicateColumnParams) -> OperationResult:
    """Copia uma coluna para logo à direita. Desconhecidos (None) são copiados como estão."""
    index = _column_index(snapshot, params.column)
    target = _check_new_column_name(snapshot, params.name)
    columns = [*snapshot.columns[: index + 1], target, *snapshot.columns[index + 1 :]]
    rows = [[*row[: index + 1], row[index], *row[index + 1 :]] for row in snapshot.rows]
    return OperationResult(
        snapshot=_with(snapshot, columns=columns, rows=rows),
        rows_affected=0,
        cells_changed=len(rows),
    )


class DeleteColumnsParams(_Strict):
    columns: list[str] = Field(min_length=1, max_length=MAX_DELETED_COLUMNS)


def _delete_columns(snapshot: Snapshot, params: DeleteColumnsParams) -> OperationResult:
    """Exclusão lógica de colunas: continuam nas versões anteriores e voltam pelo desfazer.

    Campos do mapeamento que apontavam para uma coluna excluída são removidos e avisados.
    """
    if len(set(params.columns)) != len(params.columns):
        raise DomainError("Colunas repetidas na exclusão.")
    drop = {_column_index(snapshot, name) for name in params.columns}
    if len(drop) >= len(snapshot.columns):
        raise DomainError("Não é possível excluir todas as colunas da tabela.")
    keep = [i for i in range(len(snapshot.columns)) if i not in drop]
    columns = [snapshot.columns[i] for i in keep]
    rows = [[row[i] for i in keep] for row in snapshot.rows]
    removed = {snapshot.columns[i] for i in drop}
    mapping = {f: c for f, c in snapshot.mapping.items() if c not in removed}
    warnings = [
        f"Campo '{f}' sem coluna após a exclusão ('{c}'): mapeamento removido."
        for f, c in snapshot.mapping.items()
        if c in removed
    ]
    return OperationResult(
        snapshot=_with(snapshot, columns=columns, rows=rows, mapping=mapping),
        rows_affected=len(rows),
        cells_changed=len(rows) * len(drop),
        warnings=warnings,
    )


@dataclass(frozen=True)
class OperationSpec:
    code: str
    version: int
    description: str
    params_model: type[BaseModel]
    reversible: bool
    touches_data: bool
    apply: Callable[[Snapshot, Any], OperationResult]
    # True quando o snapshot de entrada vem do arquivo original (reconstrução), não da versão atual.
    needs_original: bool = False


OPERATIONS: dict[str, OperationSpec] = {
    "rename_column": OperationSpec(
        code="rename_column",
        version=2,
        description="Renomeia uma coluna e atualiza o mapeamento. Só metadados: não copia linhas.",
        params_model=RenameColumnParams,
        reversible=True,
        touches_data=False,
        apply=_rename_column,
    ),
    "set_mapping": OperationSpec(
        code="set_mapping",
        version=1,
        description="Define o mapeamento de campos canônicos para colunas. Só metadados.",
        params_model=SetMappingParams,
        reversible=True,
        touches_data=False,
        apply=_set_mapping,
    ),
    "delete_rows": OperationSpec(
        code="delete_rows",
        version=1,
        description="Exclui logicamente linhas selecionadas (podem ser desfeitas). "
        "Os números das demais linhas são preservados.",
        params_model=DeleteRowsParams,
        reversible=True,
        touches_data=True,
        apply=_delete_rows,
    ),
    "set_header_row": OperationSpec(
        code="set_header_row",
        version=1,
        description="Escolhe a linha real do cabeçalho e reconstrói a tabela a partir do arquivo "
        "original. Gera nova versão de dados; o histórico é preservado.",
        params_model=SetHeaderParams,
        reversible=True,
        touches_data=True,
        apply=_set_header_row,
        needs_original=True,
    ),
    "apply_mapping_template": OperationSpec(
        code="apply_mapping_template",
        version=1,
        description="Aplica um modelo de mapeamento reutilizável. Só metadados.",
        params_model=ApplyTemplateParams,
        reversible=True,
        touches_data=False,
        apply=_apply_mapping_template,
    ),
    "replace_text": OperationSpec(
        code="replace_text",
        version=2,
        description="Substitui texto em uma ou mais colunas, nas linhas que casam com filtros. "
        "Desconhecidos não são alterados.",
        params_model=ReplaceTextParams,
        reversible=True,
        touches_data=True,
        apply=_replace_text,
    ),
    "set_rows_value": OperationSpec(
        code="set_rows_value",
        version=1,
        description="Define o valor de uma coluna nas linhas selecionadas "
        "(texto, vazio ou desconhecido).",
        params_model=SetRowsValueParams,
        reversible=True,
        touches_data=True,
        apply=_set_rows_value,
    ),
    "set_cells": OperationSpec(
        code="set_cells",
        version=1,
        description="Define valores em várias células (colagem). Uma única operação no histórico.",
        params_model=SetCellsParams,
        reversible=True,
        touches_data=True,
        apply=_set_cells,
    ),
    "insert_rows": OperationSpec(
        code="insert_rows",
        version=1,
        description="Insere linhas vazias após uma linha (0 = início). "
        "Números das demais preservados.",
        params_model=InsertRowsParams,
        reversible=True,
        touches_data=True,
        apply=_insert_rows,
    ),
    "duplicate_rows": OperationSpec(
        code="duplicate_rows",
        version=1,
        description="Duplica as linhas selecionadas, cada cópia logo abaixo do original.",
        params_model=DuplicateRowsParams,
        reversible=True,
        touches_data=True,
        apply=_duplicate_rows,
    ),
    "insert_column": OperationSpec(
        code="insert_column",
        version=1,
        description="Insere uma coluna vazia após outra (ou no fim). Mapeamento preservado.",
        params_model=InsertColumnParams,
        reversible=True,
        touches_data=True,
        apply=_insert_column,
    ),
    "duplicate_column": OperationSpec(
        code="duplicate_column",
        version=1,
        description="Duplica uma coluna para a direita, copiando os valores.",
        params_model=DuplicateColumnParams,
        reversible=True,
        touches_data=True,
        apply=_duplicate_column,
    ),
    "delete_columns": OperationSpec(
        code="delete_columns",
        version=1,
        description="Exclui logicamente colunas (podem ser desfeitas). "
        "Remove campos do mapeamento que apontavam para elas.",
        params_model=DeleteColumnsParams,
        reversible=True,
        touches_data=True,
        apply=_delete_columns,
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
