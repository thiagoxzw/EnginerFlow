"""Planilhas do BOM Manager (CSV e XLSX). Reutiliza o formato de exportação do Data Studio."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from engiflow_api.application import bom as app
from engiflow_api.domain.bom import BomError, BomLine, explode, find_cycles, qty_value, unit_key
from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.numeric import format_decimal
from engiflow_api.infrastructure.exporters import Sheet
from engiflow_api.infrastructure.models import Dataset

MAX_HIERARCHY_ROWS = app.MAX_EXPORT_ROWS


def lines_sheet(db: DbSession, revision_id: str) -> Sheet:
    lines = app.load_lines(db, revision_id)
    headers = [
        "Linha",
        "Conjunto pai",
        "Código",
        "Descrição",
        "Quantidade",
        "Unidade",
        "Revisão",
        "Posição",
        "Nível",
        "Código alternativo",
        "Fabricante",
        "Part number",
        "Observações",
    ]
    rows = [
        [
            str(line.line_no),
            line.parent,
            line.child,
            line.description,
            line.qty_raw,
            line.unit,
            line.rev,
            line.position,
            None if line.level is None else str(line.level),
            line.alt_code,
            line.manufacturer,
            line.part_number,
            line.notes,
        ]
        for line in lines
    ]
    return Sheet("Lista de componentes", headers, rows)


def consolidated_sheet(db: DbSession, revision_id: str, root: str, vehicles: Decimal) -> Sheet:
    result = app.do_explode(db, revision_id, root, vehicles)
    headers = ["Código", "Unidade", "Quantidade total", "Ocorrências"]
    occ = result["occurrences"]
    rows = [
        [item["code"], item["unit"], item["qty"], str(occ.get(item["code"], ""))]
        for item in result["consolidated"]
    ]
    return Sheet(f"Consolidada {format_decimal(vehicles)} veic", headers, rows)


def hierarchy_sheet(db: DbSession, revision_id: str, root: str) -> Sheet:
    """BOM hierárquica: uma linha por aparição, com nível e quantidades local e acumulada."""
    lines = app.load_lines(db, revision_id)
    if root not in {line.child for line in lines}:
        raise DomainError(f"Conjunto '{root}' não existe nesta estrutura.")
    if any(c for c in find_cycles(lines) if root in c or set(c) & _reach(lines, root)):
        raise DomainError("Ciclo detectado: exportação hierárquica recusada.")
    index: dict[str, list[BomLine]] = {}
    for line in lines:
        if line.parent and line.child:
            index.setdefault(line.parent, []).append(line)
    headers = [
        "Nível",
        "Conjunto pai",
        "Código",
        "Descrição",
        "Qtd. local",
        "Unidade local",
        "Qtd. acumulada (1 unid. do topo)",
        "Unidade",
    ]
    rows: list[list[str | None]] = []

    def walk(code: str, acc: Decimal, depth: int) -> None:
        for line in index.get(code, []):
            local = qty_value(line)
            if local is None:
                rows.append(
                    [
                        str(depth + 1),
                        code,
                        line.child,
                        line.description,
                        line.qty_raw,
                        line.unit,
                        "inválida",
                        line.unit,
                    ]
                )
                continue
            total = acc * local
            rows.append(
                [
                    str(depth + 1),
                    code,
                    line.child,
                    line.description,
                    line.qty_raw,
                    line.unit,
                    format_decimal(total),
                    unit_key(line.unit),
                ]
            )
            if len(rows) > MAX_HIERARCHY_ROWS:
                raise DomainError(
                    f"A hierarquia de '{root}' excede {MAX_HIERARCHY_ROWS} linhas (subconjuntos "
                    "compartilhados geram muitos caminhos). "
                    "Exporte um conjunto de nível mais baixo."
                )
            walk(line.child or "", total, depth + 1)

    walk(root, Decimal(1), 0)
    return Sheet(f"Hierarquia {root}"[:31], headers, rows)


def _reach(lines: list[BomLine], root: str) -> set[str]:
    index: dict[str, list[str]] = {}
    for line in lines:
        if line.parent and line.child:
            index.setdefault(line.parent, []).append(line.child)
    seen: set[str] = set()
    todo = [root]
    while todo:
        code = todo.pop()
        if code in seen:
            continue
        seen.add(code)
        todo.extend(index.get(code, []))
    return seen


def issues_sheet(db: DbSession, revision_id: str, mode: str) -> Sheet:
    result = app.do_validate(db, revision_id, mode)
    rows = [
        [
            i["severity"],
            i["rule"],
            i["message"],
            None if i["line_no"] is None else str(i["line_no"]),
            i["code"],
        ]
        for i in result["issues"]
    ]
    return Sheet("Inconsistências", ["Severidade", "Regra", "Mensagem", "Linha", "Código"], rows)


def compare_sheet(db: DbSession, revision_a: str, revision_b: str) -> Sheet:
    result = app.do_compare(db, revision_a, revision_b)
    rows = [
        [
            c["kind"],
            c["child"],
            c["parent"],
            c["detail"],
            None if c["line_no"] is None else str(c["line_no"]),
        ]
        for c in result["changes"]
    ]
    rows += [
        ["sem correspondência (removido)", code, None, None, None]
        for code in result["unmatched_removed"]
    ]
    rows += [
        ["sem correspondência (adicionado)", code, None, None, None]
        for code in result["unmatched_added"]
    ]
    rows += [
        ["possível troca de código (pendente)", p["from"], None, f"→ {p['to']}", None]
        for p in result["pending_code_changes"]
    ]
    return Sheet("Comparação", ["Tipo", "Código", "Conjunto", "Detalhe", "Linha"], rows)


def kit_sheet(
    db: DbSession, revision_id: str, parts: list[dict[str, str]], vehicles: Decimal, lot: Decimal
) -> Sheet:
    result = app.do_kit(db, revision_id, parts, vehicles, lot)
    rows = [[m["code"], m["unit"], m["qty"]] for m in result["materials"]]
    return Sheet("Separação de materiais", ["Código", "Unidade", "Quantidade para separar"], rows)


def cross_sheet(
    db: DbSession,
    revision_id: str,
    cadastro: Dataset,
    key_column: str,
    description_column: str | None,
    unit_column: str | None,
    key_mode: str,
) -> Sheet:
    result = app.do_cross(
        db,
        revision_id,
        cadastro,
        key_column=key_column,
        description_column=description_column,
        unit_column=unit_column,
        key_mode=key_mode,
    )
    rows = [
        [
            i["code"],
            i["description"],
            i["unit"],
            i["status"],
            str(i["matches"]),
            ", ".join(i["flags"]),
            ", ".join(i["equivalent_candidates"]),
        ]
        for i in result["items"]
    ]
    return Sheet(
        "Cruzamento com cadastro",
        [
            "Código",
            "Descrição",
            "Unidade",
            "Situação",
            "Correspondências",
            "Divergências",
            "Possíveis equivalentes (pendente)",
        ],
        rows,
    )


__all__ = [
    "BomError",
    "compare_sheet",
    "consolidated_sheet",
    "cross_sheet",
    "explode",
    "hierarchy_sheet",
    "issues_sheet",
    "kit_sheet",
    "lines_sheet",
]
