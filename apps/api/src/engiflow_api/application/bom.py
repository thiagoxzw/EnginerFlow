"""BOM Manager: importação com mapeamento, revisões imutáveis, edições, cruzamento e kits.

Persistência em tabelas próprias (bom_*). A origem é uma tabela do Data Studio, que já cobre CSV
e XLSX, ERP e CAD. Nada é gravado antes da confirmação; cada edição cria uma nova revisão.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from engiflow_api.domain.bom import (
    MODE_EXPLICIT,
    MODE_LEVEL,
    BomError,
    BomLine,
    KitPart,
    compare,
    defined_codes,
    duplicate_subtree,
    explode,
    find_cycles,
    kit_requirements_for_parts,
    unit_key,
    validate,
)
from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.numeric import format_decimal, parse_decimal
from engiflow_api.domain.tabular import code_key, normalize_description
from engiflow_api.infrastructure import bom_models as m
from engiflow_api.infrastructure.models import Dataset, DatasetVersionRow

# Campos canônicos do BOM. Obrigatórios: código do componente, quantidade e pai (ou nível).
FIELDS = (
    "child_code",
    "parent_code",
    "level",
    "qty",
    "unit",
    "description",
    "rev",
    "position",
    "alt_code",
    "manufacturer",
    "part_number",
    "notes",
    "category",
)
REQUIRED_ALWAYS = ("child_code", "qty")
MAX_LINES = 50_000
MAX_EXPORT_ROWS = 200_000


def _clean_code(value: str | None) -> str | None:
    """Código: remove espaços das pontas, preserva zeros e caracteres. Vazio vira ausente (None)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _cell(values: list[str | None], index: int | None) -> str | None:
    if index is None or index >= len(values):
        return None
    return values[index]


def _level(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    return int(text) if text.isdigit() else None


def required_fields(mode: str) -> tuple[str, ...]:
    """Campos obrigatórios conforme o modo: pai explícito, ou nível hierárquico."""
    if mode == MODE_LEVEL:
        return (*REQUIRED_ALWAYS, "level")
    return (*REQUIRED_ALWAYS, "parent_code")


def validate_mapping(mapping: dict[str, str], columns: list[str], mode: str) -> dict[str, str]:
    unknown = sorted(set(mapping) - set(FIELDS))
    if unknown:
        raise DomainError(f"Campos desconhecidos no mapeamento: {', '.join(unknown)}.")
    missing_column = sorted({c for c in mapping.values() if c not in columns})
    if missing_column:
        raise DomainError(f"Colunas inexistentes na tabela: {', '.join(missing_column)}.")
    missing = [f for f in required_fields(mode) if f not in mapping]
    if missing:
        raise DomainError(f"Campos obrigatórios sem coluna: {', '.join(missing)}.")
    if mode not in (MODE_EXPLICIT, MODE_LEVEL):
        raise DomainError("Modo de hierarquia inválido.")
    return dict(mapping)


def read_dataset(
    db: DbSession, dataset: Dataset
) -> tuple[list[str], list[tuple[int, list[str | None]]]]:
    """Linhas da versão atual da tabela, na ordem do arquivo."""
    if dataset.current_version_id is None:
        raise DomainError("Tabela sem versão atual.")
    rows = db.execute(
        select(DatasetVersionRow.row_number, DatasetVersionRow.values)
        .where(DatasetVersionRow.version_id == dataset.current_version_id)
        .order_by(DatasetVersionRow.row_number)
    ).all()
    if len(rows) > MAX_LINES:
        raise DomainError(f"A estrutura tem {len(rows)} linhas. O limite é {MAX_LINES}.")
    return list(dataset.columns), [(int(n), list(v)) for n, v in rows]


def build_lines(
    columns: list[str],
    rows: list[tuple[int, list[str | None]]],
    mapping: dict[str, str],
    mode: str,
) -> list[BomLine]:
    """Converte linhas da tabela em linhas de BOM, sem inventar relacionamento.

    Modo explícito: o pai vem da coluna de pai. Modo por nível: o pai é a última linha do nível
    anterior (marcado como inferido). Sem nível anterior, o pai fica vazio e a validação aponta.
    """
    index = {field: columns.index(col) for field, col in mapping.items()}
    lines: list[BomLine] = []
    last_at_level: dict[int, str] = {}
    for line_no, (row_number, values) in enumerate(rows, start=1):
        child = _clean_code(_cell(values, index.get("child_code")))
        qty_raw = _clean_text(_cell(values, index.get("qty")))
        level = _level(_cell(values, index.get("level")))
        parent: str | None
        inferred = False
        if mode == MODE_LEVEL:
            parent = None
            if level is not None and level > 1:
                parent = last_at_level.get(level - 1)
                inferred = parent is not None
            if level is not None:
                for deeper in [k for k in last_at_level if k >= level]:
                    del last_at_level[deeper]
                if child:
                    last_at_level[level] = child
        else:
            parent = _clean_code(_cell(values, index.get("parent_code")))
        lines.append(
            BomLine(
                line_no=line_no,
                parent=parent,
                child=child,
                description=_clean_text(_cell(values, index.get("description"))),
                qty_raw=qty_raw,
                unit=_clean_text(_cell(values, index.get("unit"))),
                rev=_clean_text(_cell(values, index.get("rev"))),
                position=_clean_text(_cell(values, index.get("position"))),
                level=level,
                alt_code=_clean_code(_cell(values, index.get("alt_code"))),
                manufacturer=_clean_text(_cell(values, index.get("manufacturer"))),
                part_number=_clean_text(_cell(values, index.get("part_number"))),
                notes=_clean_text(_cell(values, index.get("notes"))),
                category=_clean_text(_cell(values, index.get("category"))),
                source_row=row_number,
                inferred_parent=inferred,
            )
        )
    if len(lines) > MAX_LINES:
        raise DomainError(f"A estrutura tem {len(lines)} linhas. O limite é {MAX_LINES}.")
    return lines


def preview(db: DbSession, dataset: Dataset, mapping: dict[str, str], mode: str) -> dict[str, Any]:
    """Prévia antes de confirmar: contagens, raízes, avisos e amostra da árvore. Não grava nada."""
    columns, rows = read_dataset(db, dataset)
    mapping = validate_mapping(mapping, columns, mode)
    lines = build_lines(columns, rows, mapping, mode)
    issues = validate(lines, mode)
    roots = sorted({line.child for line in lines if not line.parent and line.child})
    by_severity: dict[str, int] = defaultdict(int)
    for issue in issues:
        by_severity[issue.severity] += 1
    return {
        "line_count": len(lines),
        "roots": roots,
        "issue_counts": dict(by_severity),
        "issues": [_issue_out(i) for i in issues[:200]],
        "inferred_parents": sum(1 for line in lines if line.inferred_parent),
        "sample": [_line_out(line) for line in lines[:100]],
    }


def _issue_out(issue: Any) -> dict[str, Any]:
    return asdict(issue)


def _line_out(line: BomLine) -> dict[str, Any]:
    return {
        "line_no": line.line_no,
        "source_row": line.source_row,
        "parent": line.parent,
        "child": line.child,
        "description": line.description,
        "qty": line.qty_raw,
        "unit": line.unit,
        "rev": line.rev,
        "position": line.position,
        "level": line.level,
        "alt_code": line.alt_code,
        "manufacturer": line.manufacturer,
        "part_number": line.part_number,
        "notes": line.notes,
        "category": line.category,
        "inferred_parent": line.inferred_parent,
    }


def _digest(lines: list[BomLine]) -> str:
    payload = json.dumps([asdict(line) for line in lines], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _next_number(db: DbSession, structure_id: str) -> int:
    # Trava a linha da estrutura até o commit: duas edições simultâneas não recebem o mesmo número.
    db.execute(
        select(m.BomStructure.id).where(m.BomStructure.id == structure_id).with_for_update()
    ).first()
    value = db.scalar(
        select(func.coalesce(func.max(m.BomRevision.number), 0)).where(
            m.BomRevision.structure_id == structure_id
        )
    )
    return int(value or 0) + 1


def _write_revision(
    db: DbSession,
    structure: m.BomStructure,
    lines: list[BomLine],
    *,
    label: str,
    mapping: dict[str, str],
    mode: str,
    source_dataset_id: str | None,
    source_version_id: str | None,
    parent_revision_id: str | None,
    actor: str,
) -> m.BomRevision:
    revision = m.BomRevision(
        structure_id=structure.id,
        number=_next_number(db, structure.id),
        label=label[:160],
        parent_revision_id=parent_revision_id,
        source_dataset_id=source_dataset_id,
        source_version_id=source_version_id,
        mapping=dict(mapping),
        mode=mode,
        line_count=len(lines),
        content_sha256=_digest(lines),
        actor=actor,
    )
    db.add(revision)
    db.flush()
    for line in lines:
        db.add(
            m.BomLine(
                revision_id=revision.id,
                line_no=line.line_no,
                source_row=line.source_row,
                parent_code=line.parent,
                child_code=line.child,
                description=line.description,
                qty_raw=line.qty_raw,
                unit=line.unit,
                rev=line.rev,
                position=line.position,
                level=line.level,
                alt_code=line.alt_code,
                manufacturer=line.manufacturer,
                part_number=line.part_number,
                notes=line.notes,
                category=line.category,
                inferred_parent=line.inferred_parent,
            )
        )
    db.flush()
    return revision


def create_structure(
    db: DbSession,
    *,
    name: str,
    description: str,
    dataset: Dataset,
    mapping: dict[str, str],
    mode: str,
    actor: str,
) -> tuple[m.BomStructure, m.BomRevision]:
    clean_name = name.strip()
    if not clean_name:
        raise DomainError("Informe o nome da estrutura.")
    if db.scalar(select(m.BomStructure).where(m.BomStructure.name == clean_name)) is not None:
        raise DomainError(f"Já existe uma estrutura chamada '{clean_name}'.")
    columns, rows = read_dataset(db, dataset)
    mapping = validate_mapping(mapping, columns, mode)
    lines = build_lines(columns, rows, mapping, mode)
    structure = m.BomStructure(name=clean_name, description=description.strip()[:1000])
    db.add(structure)
    db.flush()
    revision = _write_revision(
        db,
        structure,
        lines,
        label="Importação inicial",
        mapping=mapping,
        mode=mode,
        source_dataset_id=dataset.id,
        source_version_id=dataset.current_version_id,
        parent_revision_id=None,
        actor=actor,
    )
    structure.current_revision_id = revision.id
    db.flush()
    return structure, revision


def get_structure(db: DbSession, structure_id: str) -> m.BomStructure:
    structure = db.get(m.BomStructure, structure_id)
    if structure is None or structure.deleted_at is not None:
        raise DomainError("Estrutura não encontrada.")
    return structure


def get_revision(db: DbSession, revision_id: str) -> m.BomRevision:
    revision = db.get(m.BomRevision, revision_id)
    if revision is None:
        raise DomainError("Revisão não encontrada.")
    return revision


def load_lines(db: DbSession, revision_id: str) -> list[BomLine]:
    rows = db.scalars(
        select(m.BomLine).where(m.BomLine.revision_id == revision_id).order_by(m.BomLine.line_no)
    ).all()
    return [
        BomLine(
            line_no=r.line_no,
            parent=r.parent_code,
            child=r.child_code,
            description=r.description,
            qty_raw=r.qty_raw,
            unit=r.unit,
            rev=r.rev,
            position=r.position,
            level=r.level,
            alt_code=r.alt_code,
            manufacturer=r.manufacturer,
            part_number=r.part_number,
            notes=r.notes,
            category=r.category,
            source_row=r.source_row,
            inferred_parent=r.inferred_parent,
        )
        for r in rows
    ]


def list_revisions(db: DbSession, structure_id: str) -> list[m.BomRevision]:
    return list(
        db.scalars(
            select(m.BomRevision)
            .where(m.BomRevision.structure_id == structure_id)
            .order_by(m.BomRevision.number)
        ).all()
    )


def set_current(db: DbSession, structure: m.BomStructure, revision_id: str) -> None:
    """Desfazer/refazer de revisão: aponta a atual para uma revisão existente. Nada é apagado."""
    revision = get_revision(db, revision_id)
    if revision.structure_id != structure.id:
        raise DomainError("A revisão não pertence a esta estrutura.")
    structure.current_revision_id = revision.id
    db.flush()


def edit_revision(
    db: DbSession,
    structure: m.BomStructure,
    base: m.BomRevision,
    edits: list[dict[str, Any]],
    *,
    actor: str,
) -> m.BomRevision:
    """Aplica edições e grava uma NOVA revisão. A revisão de origem permanece intacta."""
    if not edits:
        raise DomainError("Nenhuma alteração informada.")
    if len(edits) > 500:
        raise DomainError("Muitas alterações de uma vez (limite 500).")
    lines = load_lines(db, base.id)
    next_no = max((line.line_no for line in lines), default=0) + 1
    for edit in edits:
        lines, next_no = _apply_edit(lines, edit, next_no)
    cycles = find_cycles(lines)
    if cycles:
        raise DomainError(f"A alteração criaria referência circular: {' → '.join(cycles[0])}.")
    lines = _renumber(lines)
    revision = _write_revision(
        db,
        structure,
        lines,
        label=f"Alteração sobre r{base.number}",
        mapping=base.mapping,
        mode=base.mode,
        source_dataset_id=base.source_dataset_id,
        source_version_id=base.source_version_id,
        parent_revision_id=base.id,
        actor=actor,
    )
    structure.current_revision_id = revision.id
    db.flush()
    return revision


def _renumber(lines: list[BomLine]) -> list[BomLine]:
    return [BomLine(**{**asdict(line), "line_no": i}) for i, line in enumerate(lines, start=1)]


def _apply_edit(
    lines: list[BomLine], edit: dict[str, Any], next_no: int
) -> tuple[list[BomLine], int]:
    op = str(edit.get("op", ""))
    if op == "add_line":
        parent = _clean_code(edit.get("parent"))
        child = _clean_code(edit.get("child"))
        qty = _clean_text(edit.get("qty"))
        if not parent or not child or not qty:
            raise DomainError("Inclusão exige conjunto pai, componente e quantidade.")
        if parent not in defined_codes(lines):
            raise DomainError(f"Conjunto pai '{parent}' não existe nesta estrutura.")
        new = BomLine(
            line_no=next_no,
            parent=parent,
            child=child,
            description=_clean_text(edit.get("description")),
            qty_raw=qty,
            unit=_clean_text(edit.get("unit")),
            rev=_clean_text(edit.get("rev")),
            position=_clean_text(edit.get("position")),
        )
        return [*lines, new], next_no + 1
    if op == "remove_line":
        target = _line_no(edit)
        return [line for line in lines if line.line_no != target], next_no
    if op == "set_qty":
        target = _line_no(edit)
        qty = _clean_text(edit.get("qty"))
        if not qty:
            raise DomainError("Informe a nova quantidade.")
        return [
            _with(line, qty_raw=qty) if line.line_no == target else line for line in lines
        ], next_no
    if op == "set_description":
        description = _clean_text(edit.get("description"))
        if "line_no" in edit:
            target = _line_no(edit)
            return [
                _with(line, description=description) if line.line_no == target else line
                for line in lines
            ], next_no
        code = _clean_code(edit.get("code"))
        if not code:
            raise DomainError("Informe a linha ou o código do componente.")
        return [
            _with(line, description=description) if line.child == code else line for line in lines
        ], next_no
    if op == "move_line":
        target = _line_no(edit)
        parent = _clean_code(edit.get("parent"))
        if not parent or parent not in defined_codes(lines):
            raise DomainError(f"Conjunto de destino '{parent}' não existe nesta estrutura.")
        return [
            _with(line, parent=parent) if line.line_no == target else line for line in lines
        ], next_no
    if op == "duplicate_subtree":
        code = _clean_code(edit.get("code"))
        new_code = _clean_code(edit.get("new_code"))
        if not code or not new_code:
            raise DomainError("Informe o conjunto e o novo código.")
        try:
            subtree_lines, _ = duplicate_subtree(lines, code, new_code, next_no)
        except BomError as exc:
            raise DomainError(str(exc)) from exc
        return [*lines, *subtree_lines], next_no + len(subtree_lines)
    if op == "duplicate_subassembly":
        code = _clean_code(edit.get("code"))
        new_code = _clean_code(edit.get("new_code"))
        if not code or not new_code:
            raise DomainError("Informe o conjunto e o novo código.")
        if code not in defined_codes(lines):
            raise DomainError(f"Conjunto '{code}' não existe nesta estrutura.")
        if new_code in defined_codes(lines):
            raise DomainError(f"O código '{new_code}' já existe nesta estrutura.")
        added: list[BomLine] = []
        n = next_no
        for line in lines:
            if (
                line.child == code
            ):  # o conjunto passa a existir também com o novo código, nos mesmos pais
                added.append(_with(line, line_no=n, child=new_code))
                n += 1
            if line.parent == code:  # filhos diretos passam a compor o novo conjunto
                added.append(_with(line, line_no=n, parent=new_code))
                n += 1
        return [*lines, *added], n
    raise DomainError(f"Alteração desconhecida: '{op}'.")


def _line_no(edit: dict[str, Any]) -> int:
    value = edit.get("line_no")
    if not isinstance(value, int):
        raise DomainError("Informe o número da linha.")
    return value


def _with(line: BomLine, **changes: Any) -> BomLine:
    return BomLine(**{**asdict(line), **changes})


def do_explode(db: DbSession, revision_id: str, root: str, vehicles: Decimal) -> dict[str, Any]:
    lines = load_lines(db, revision_id)
    try:
        result = explode(lines, root, vehicles)
    except BomError as exc:
        raise DomainError(str(exc)) from exc
    consolidated = [
        {"code": code, "unit": unit, "qty": format_decimal(qty)}
        for (code, unit), qty in sorted(result.consolidated.items())
    ]
    return {
        "root": root,
        "vehicles": format_decimal(vehicles),
        "consolidated": consolidated,
        "occurrences": dict(sorted(result.occurrences.items())),
        "invalid_lines": result.invalid_lines,
        "warnings": result.warnings,
    }


def do_compare(db: DbSession, revision_a: str, revision_b: str) -> dict[str, Any]:
    a = load_lines(db, revision_a)
    b = load_lines(db, revision_b)
    result = compare(a, b)
    return {
        "counts": result.counts(),
        "changes": [asdict(c) for c in result.changes],
        "unmatched_removed": result.unmatched_removed,
        "unmatched_added": result.unmatched_added,
        "pending_code_changes": [
            {"from": o, "to": n, "status": "pendente"} for o, n in result.pending_code_changes
        ],
    }


def do_validate(db: DbSession, revision_id: str, mode: str) -> dict[str, Any]:
    lines = load_lines(db, revision_id)
    issues = validate(lines, mode)
    counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        counts[issue.severity] += 1
    return {"counts": dict(counts), "issues": [asdict(i) for i in issues]}


def do_cross(
    db: DbSession,
    revision_id: str,
    cadastro: Dataset,
    *,
    key_column: str,
    description_column: str | None,
    unit_column: str | None,
    key_mode: str,
) -> dict[str, Any]:
    """Cruza os códigos da estrutura com um cadastro configurável. Nunca atribui código sozinho."""
    lines = load_lines(db, revision_id)
    columns, rows = read_dataset(db, cadastro)
    for col in (key_column, description_column, unit_column):
        if col is not None and col not in columns:
            raise DomainError(f"Coluna '{col}' não existe no cadastro.")
    if key_mode not in ("exato", "normalizado"):
        raise DomainError("Modo de comparação de códigos inválido.")

    def key_of(value: str) -> str:
        return value if key_mode == "exato" else code_key(value)

    k = columns.index(key_column)
    d = columns.index(description_column) if description_column else None
    u = columns.index(unit_column) if unit_column else None
    index: dict[str, list[tuple[str | None, str | None]]] = defaultdict(list)
    by_description: dict[str, list[str]] = defaultdict(list)
    for _, values in rows:
        code = _clean_code(values[k] if k < len(values) else None)
        if not code:
            continue
        desc = _clean_text(values[d]) if d is not None and d < len(values) else None
        unit = _clean_text(values[u]) if u is not None and u < len(values) else None
        index[key_of(code)].append((desc, unit))
        if desc:
            by_description[normalize_description(desc)].append(code)

    bom_items: dict[str, BomLine] = {}
    missing_code = 0
    for line in lines:
        if not line.child:
            missing_code += 1
            continue
        bom_items.setdefault(line.child, line)
    results: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for code, line in sorted(bom_items.items()):
        matches = index.get(key_of(code), [])
        entry: dict[str, Any] = {
            "code": code,
            "description": line.description,
            "unit": line.unit,
            "matches": len(matches),
            "status": "",
            "flags": [],
            "equivalent_candidates": [],
        }
        if not matches:
            entry["status"] = "sem_cadastro"
            desc_key = normalize_description(line.description or "")
            if desc_key:
                candidates = [
                    c for c in by_description.get(desc_key, []) if key_of(c) != key_of(code)
                ]
                if candidates:
                    entry["status"] = "possivel_equivalente"
                    entry["equivalent_candidates"] = sorted(set(candidates))[:20]
        elif len(matches) > 1:
            entry["status"] = "multiplas_correspondencias"
        else:
            entry["status"] = "encontrado"
            cad_desc, cad_unit = matches[0]
            if (
                cad_desc
                and line.description
                and normalize_description(cad_desc) != normalize_description(line.description)
            ):
                entry["flags"].append("descricao_divergente")
            if (
                u is not None
                and cad_unit
                and line.unit
                and cad_unit.strip().upper() != line.unit.strip().upper()
            ):
                entry["flags"].append("unidade_divergente")
        counts[entry["status"]] += 1
        for flag in entry["flags"]:
            counts[flag] += 1
        results.append(entry)
    counts["codigo_ausente"] = missing_code
    return {"counts": dict(counts), "items": results, "key_mode": key_mode}


def add_kit(
    db: DbSession, structure: m.BomStructure, name: str, parts: list[dict[str, str]]
) -> m.BomKit:
    clean = name.strip()
    if not clean:
        raise DomainError("Informe o nome do kit.")
    if not parts:
        raise DomainError("O kit precisa de ao menos um subconjunto.")
    kit = m.BomKit(structure_id=structure.id, name=clean[:160], parts=parts)
    db.add(kit)
    db.flush()
    return kit


def do_kit(
    db: DbSession, revision_id: str, parts: list[dict[str, str]], vehicles: Decimal, lot: Decimal
) -> dict[str, Any]:
    lines = load_lines(db, revision_id)
    kit_parts = [
        KitPart(
            code=p["code"], qty=parse_decimal(p["qty"]) or Decimal(0), unit=p.get("unit") or None
        )
        for p in parts
    ]
    try:
        total = kit_requirements_for_parts(lines, kit_parts, vehicles, lot)
    except BomError as exc:
        raise DomainError(str(exc)) from exc
    return {
        "vehicles": format_decimal(vehicles),
        "lot": format_decimal(lot),
        "materials": [
            {"code": code, "unit": unit, "qty": format_decimal(qty)}
            for (code, unit), qty in sorted(total.items())
        ],
    }


KIT_FIELDS = ("code", "qty", "unit", "description")


def kit_rows_from_dataset(
    db: DbSession,
    structure_id: str,
    dataset: Dataset,
    mapping: dict[str, str],
) -> dict[str, Any]:
    """Prévia de kit a partir de uma tabela do Data Studio (CSV ou XLSX já importados).

    Campos: código (obrigatório), quantidade (obrigatória), unidade e descrição (opcionais).
    Linhas com o mesmo código e unidade são somadas e isso é informado. Nada é gravado aqui.
    """
    columns, rows = read_dataset(db, dataset)
    unknown = sorted(set(mapping) - set(KIT_FIELDS))
    if unknown:
        raise DomainError(f"Campos desconhecidos no kit: {', '.join(unknown)}.")
    for field in ("code", "qty"):
        if field not in mapping:
            raise DomainError(f"Campo obrigatório sem coluna: {field}.")
        if mapping[field] not in columns:
            raise DomainError(f"Coluna '{mapping[field]}' não existe na tabela.")
    index = {field: columns.index(col) for field, col in mapping.items() if col in columns}
    structure = get_structure(db, structure_id)
    lines = load_lines(db, structure.current_revision_id or "")
    known = defined_codes(lines)
    issues: list[dict[str, Any]] = []
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row_number, values in rows:
        code = _clean_code(_cell(values, index.get("code")))
        qty_text = _clean_text(_cell(values, index.get("qty")))
        unit = _clean_text(_cell(values, index.get("unit")))
        if not code:
            issues.append({"severity": "erro", "row": row_number, "message": "Linha sem código."})
            continue
        qty = parse_decimal(qty_text)
        if qty is None or qty <= 0:
            issues.append(
                {
                    "severity": "erro",
                    "row": row_number,
                    "code": code,
                    "message": f"Quantidade inválida: '{qty_text or ''}'.",
                }
            )
            continue
        if code not in known:
            issues.append(
                {
                    "severity": "erro",
                    "row": row_number,
                    "code": code,
                    "message": "Código não existe nesta estrutura.",
                }
            )
        key = (code, unit_key(unit) if unit else "")
        if key in merged:
            merged[key]["qty"] = merged[key]["qty"] + qty
            issues.append(
                {
                    "severity": "informação",
                    "row": row_number,
                    "code": code,
                    "message": "Mesmo código e unidade: quantidades somadas.",
                }
            )
        else:
            merged[key] = {
                "code": code,
                "qty": qty,
                "unit": unit,
                "description": _clean_text(_cell(values, index.get("description"))),
            }
    units_by_code: dict[str, set[str]] = defaultdict(set)
    for code_key_value, unit_value in merged:
        units_by_code[code_key_value].add(unit_value)
    for code_value, units in sorted(units_by_code.items()):
        if len(units) > 1:
            issues.append(
                {
                    "severity": "informação",
                    "row": None,
                    "code": code_value,
                    "message": _units_message(code_value, units),
                }
            )
    parts = [
        {
            "code": p["code"],
            "qty": format_decimal(p["qty"]),
            "unit": p["unit"],
            "description": p["description"],
        }
        for p in merged.values()
    ]
    return {"parts": parts, "issues": issues, "row_count": len(rows)}


def add_kit_from_dataset(
    db: DbSession,
    structure: m.BomStructure,
    name: str,
    dataset: Dataset,
    mapping: dict[str, str],
) -> m.BomKit:
    preview_data = kit_rows_from_dataset(db, structure.id, dataset, mapping)
    errors = [i for i in preview_data["issues"] if i["severity"] == "erro"]
    if errors:
        raise DomainError(
            f"A tabela tem {len(errors)} erro(s) de kit. Corrija antes de criar o kit."
        )
    if not preview_data["parts"]:
        raise DomainError("A tabela não tem componentes válidos para o kit.")
    return add_kit(db, structure, name, preview_data["parts"])


def _units_message(code: str, units: set[str]) -> str:
    listed = ", ".join(sorted(u or "(sem unidade)" for u in units))
    return (
        f"Mesmo código '{code}' com unidades diferentes ({listed}): "
        "tratados em linhas separadas, não somados."
    )
