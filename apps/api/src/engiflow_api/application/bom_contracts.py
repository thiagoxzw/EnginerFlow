"""Contratos internos do BOM Manager para módulos futuros (Material Manager, Solid Edge, Inventory,
ERP). Somente leitura: os módulos consultam estes formatos, não as tabelas `bom_*`.

Versão do contrato: 1. Mudanças incompatíveis exigem nova versão e nota em docs/architecture.
Valores de quantidade e códigos são texto (zeros à esquerda e caracteres são preservados).
"""

from __future__ import annotations

from typing import TypedDict


class RevisionContract(TypedDict):
    id: str
    number: int
    label: str
    parent_revision_id: str | None
    source_dataset_id: str | None
    mode: str
    line_count: int
    content_sha256: str
    actor: str
    created_at: str | None


class StructureContract(TypedDict):
    id: str
    name: str
    description: str
    current_revision_id: str | None
    revisions: list[RevisionContract]


class ComponentLineContract(TypedDict):
    """Uma aparição de componente em uma revisão. Um código pode ter várias linhas (vários pais)."""

    line_no: int
    source_row: int | None
    parent: str | None
    child: str | None
    description: str | None
    qty: str | None
    unit: str | None
    rev: str | None
    position: str | None
    level: int | None
    alt_code: str | None
    manufacturer: str | None
    part_number: str | None
    notes: str | None
    category: str | None
    inferred_parent: bool


class ConsolidatedQuantityContract(TypedDict):
    """Quantidade consolidada por código e unidade (nunca soma unidades diferentes)."""

    code: str
    unit: str
    qty: str


class ExplosionContract(TypedDict):
    root: str
    vehicles: str
    consolidated: list[ConsolidatedQuantityContract]
    occurrences: dict[str, int]
    invalid_lines: list[int]
    warnings: list[str]


class IssueContract(TypedDict):
    severity: str  # "erro" | "alerta" | "informação"
    rule: str
    message: str
    line_no: int | None
    code: str | None


class ValidationResultContract(TypedDict):
    counts: dict[str, int]
    issues: list[IssueContract]


class ComparisonContract(TypedDict):
    counts: dict[str, int]
    changes: list[dict[str, object]]
    unmatched_removed: list[str]
    unmatched_added: list[str]
    pending_code_changes: list[dict[str, str]]


class KitPartContract(TypedDict):
    code: str
    qty: str
    unit: str | None


class KitContract(TypedDict):
    id: str
    name: str
    parts: list[KitPartContract]


class KitMaterialsContract(TypedDict):
    vehicles: str
    lot: str
    materials: list[ConsolidatedQuantityContract]


CONTRACT_VERSION = 1
