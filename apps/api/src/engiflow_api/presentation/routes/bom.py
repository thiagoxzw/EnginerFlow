"""Rotas do BOM Manager (Fase 4). Todas exigem sessão e registram auditoria nas escritas."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application import bom as app
from engiflow_api.application import bom_export as bx
from engiflow_api.application.audit import record_event
from engiflow_api.application.data_studio import get_dataset
from engiflow_api.domain.errors import DomainError
from engiflow_api.infrastructure.exporters import to_csv_bytes, to_xlsx_bytes
from engiflow_api.infrastructure.models import Dataset
from engiflow_api.presentation.deps import CurrentUser, DbDep

router = APIRouter(prefix="/api/v1/bom", tags=["bom"])

Mode = Literal["explicit", "level"]
MappingIn = dict[str, str]


def _correlation(request: Request) -> str | None:
    value: str | None = getattr(request.state, "correlation_id", None)
    return value


def _dataset(db: DbSession, dataset_id: str) -> Dataset:
    return get_dataset(db, dataset_id)


class PreviewIn(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=36)
    mapping: MappingIn = Field(default_factory=dict)
    mode: Mode = "explicit"


class StructureIn(PreviewIn):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)


class CurrentIn(BaseModel):
    revision_id: str = Field(min_length=1, max_length=36)


class EditsIn(BaseModel):
    edits: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


class ExplodeIn(BaseModel):
    root: str = Field(min_length=1, max_length=255)
    vehicles: Decimal = Field(default=Decimal(1), gt=0, le=1_000_000)


class CompareIn(BaseModel):
    revision_a: str = Field(min_length=1, max_length=36)
    revision_b: str = Field(min_length=1, max_length=36)


class CrossIn(BaseModel):
    cadastro_dataset_id: str = Field(min_length=1, max_length=36)
    key_column: str = Field(min_length=1, max_length=255)
    description_column: str | None = None
    unit_column: str | None = None
    key_mode: Literal["exato", "normalizado"] = "exato"


class KitPart(BaseModel):
    unit: str | None = Field(default=None, max_length=32)
    code: str = Field(min_length=1, max_length=255)
    qty: str = Field(min_length=1, max_length=64)


class KitIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    parts: list[KitPart] = Field(min_length=1, max_length=200)


class KitCalcIn(BaseModel):
    parts: list[KitPart] = Field(min_length=1, max_length=200)
    vehicles: Decimal = Field(default=Decimal(1), gt=0, le=1_000_000)
    lot: Decimal = Field(default=Decimal(1), gt=0, le=1_000_000)


def _structure_out(db: DbSession, structure: Any) -> dict[str, Any]:
    revisions = app.list_revisions(db, structure.id)
    return {
        "id": structure.id,
        "name": structure.name,
        "description": structure.description,
        "current_revision_id": structure.current_revision_id,
        "revisions": [_revision_out(r) for r in revisions],
    }


def _revision_out(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "number": r.number,
        "label": r.label,
        "parent_revision_id": r.parent_revision_id,
        "source_dataset_id": r.source_dataset_id,
        "mode": r.mode,
        "line_count": r.line_count,
        "content_sha256": r.content_sha256,
        "actor": r.actor,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("/preview")
def preview(payload: PreviewIn, user: CurrentUser, db: DbDep) -> dict[str, Any]:
    """Prévia da estrutura antes de confirmar a importação. Não grava nada."""
    return app.preview(db, _dataset(db, payload.dataset_id), payload.mapping, payload.mode)


@router.post("/structures", status_code=201)
def create_structure(
    payload: StructureIn, request: Request, user: CurrentUser, db: DbDep
) -> dict[str, Any]:
    structure, revision = app.create_structure(
        db,
        name=payload.name,
        description=payload.description,
        dataset=_dataset(db, payload.dataset_id),
        mapping=payload.mapping,
        mode=payload.mode,
        actor=user.email,
    )
    record_event(
        db,
        actor=user.email,
        action="bom.structure.create",
        resource=f"bom:{structure.id}",
        result="ok",
        correlation_id=_correlation(request),
        details={"revision": revision.id},
    )
    db.commit()
    return {"structure": _structure_out(db, structure), "revision_id": revision.id}


@router.get("/structures")
def list_structures(user: CurrentUser, db: DbDep) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from engiflow_api.infrastructure.bom_models import BomStructure

    rows = db.scalars(
        select(BomStructure).where(BomStructure.deleted_at.is_(None)).order_by(BomStructure.name)
    ).all()
    return [_structure_out(db, s) for s in rows]


@router.get("/structures/{structure_id}")
def get_structure(structure_id: str, user: CurrentUser, db: DbDep) -> dict[str, Any]:
    return _structure_out(db, app.get_structure(db, structure_id))


@router.post("/structures/{structure_id}/current")
def set_current(
    structure_id: str, payload: CurrentIn, request: Request, user: CurrentUser, db: DbDep
) -> dict[str, Any]:
    """Desfazer e refazer entre revisões: aponta a revisão atual. Nenhuma revisão é removida."""
    structure = app.get_structure(db, structure_id)
    app.set_current(db, structure, payload.revision_id)
    record_event(
        db,
        actor=user.email,
        action="bom.structure.current",
        resource=f"bom:{structure.id}",
        result="ok",
        correlation_id=_correlation(request),
        details={"revision": payload.revision_id},
    )
    db.commit()
    return _structure_out(db, structure)


@router.get("/revisions/{revision_id}/lines")
def lines(revision_id: str, user: CurrentUser, db: DbDep) -> dict[str, Any]:
    app.get_revision(db, revision_id)
    items = app.load_lines(db, revision_id)
    return {"revision_id": revision_id, "lines": [app._line_out(line) for line in items]}


@router.post("/revisions/{revision_id}/edits", status_code=201)
def edit(
    revision_id: str, payload: EditsIn, request: Request, user: CurrentUser, db: DbDep
) -> dict[str, Any]:
    """Edições criam uma NOVA revisão; a anterior permanece."""
    base = app.get_revision(db, revision_id)
    structure = app.get_structure(db, base.structure_id)
    new = app.edit_revision(db, structure, base, payload.edits, actor=user.email)
    record_event(
        db,
        actor=user.email,
        action="bom.revision.edit",
        resource=f"bom:{structure.id}",
        result="ok",
        correlation_id=_correlation(request),
        details={"base": base.id, "new": new.id, "operations": len(payload.edits)},
    )
    db.commit()
    return {"revision": _revision_out(new), "structure": _structure_out(db, structure)}


@router.post("/revisions/{revision_id}/explode")
def explode_route(
    revision_id: str, payload: ExplodeIn, user: CurrentUser, db: DbDep
) -> dict[str, Any]:
    return app.do_explode(db, revision_id, payload.root, payload.vehicles)


@router.post("/compare")
def compare_route(payload: CompareIn, user: CurrentUser, db: DbDep) -> dict[str, Any]:
    app.get_revision(db, payload.revision_a)
    app.get_revision(db, payload.revision_b)
    return app.do_compare(db, payload.revision_a, payload.revision_b)


@router.get("/revisions/{revision_id}/validate")
def validate_route(
    revision_id: str,
    user: CurrentUser,
    db: DbDep,
    mode: Annotated[Mode, Query()] = "explicit",
) -> dict[str, Any]:
    app.get_revision(db, revision_id)
    return app.do_validate(db, revision_id, mode)


@router.post("/revisions/{revision_id}/cross")
def cross_route(revision_id: str, payload: CrossIn, user: CurrentUser, db: DbDep) -> dict[str, Any]:
    app.get_revision(db, revision_id)
    return app.do_cross(
        db,
        revision_id,
        _dataset(db, payload.cadastro_dataset_id),
        key_column=payload.key_column,
        description_column=payload.description_column,
        unit_column=payload.unit_column,
        key_mode=payload.key_mode,
    )


@router.post("/structures/{structure_id}/kits", status_code=201)
def create_kit(
    structure_id: str, payload: KitIn, request: Request, user: CurrentUser, db: DbDep
) -> dict[str, Any]:
    structure = app.get_structure(db, structure_id)
    kit = app.add_kit(db, structure, payload.name, [p.model_dump() for p in payload.parts])
    record_event(
        db,
        actor=user.email,
        action="bom.kit.create",
        resource=f"bom:{structure.id}",
        result="ok",
        correlation_id=_correlation(request),
        details={"kit": kit.id},
    )
    db.commit()
    return {"id": kit.id, "name": kit.name, "parts": kit.parts}


@router.get("/structures/{structure_id}/kits")
def list_kits(structure_id: str, user: CurrentUser, db: DbDep) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from engiflow_api.infrastructure.bom_models import BomKit

    app.get_structure(db, structure_id)
    kits = db.scalars(
        select(BomKit).where(BomKit.structure_id == structure_id).order_by(BomKit.name)
    ).all()
    return [{"id": k.id, "name": k.name, "parts": k.parts} for k in kits]


@router.post("/revisions/{revision_id}/kit-calc")
def kit_calc(revision_id: str, payload: KitCalcIn, user: CurrentUser, db: DbDep) -> dict[str, Any]:
    return app.do_kit(
        db, revision_id, [p.model_dump() for p in payload.parts], payload.vehicles, payload.lot
    )


ExportKind = Literal["lines", "consolidated", "hierarchy", "issues", "compare", "kit", "cross"]


@router.get("/revisions/{revision_id}/export")
def export(
    revision_id: str,
    user: CurrentUser,
    db: DbDep,
    kind: Annotated[ExportKind, Query()],
    fmt: Annotated[Literal["csv", "xlsx"], Query()] = "xlsx",
    root: Annotated[str | None, Query(max_length=255)] = None,
    vehicles: Annotated[Decimal, Query(gt=0, le=1_000_000)] = Decimal(1),
    other_revision: Annotated[str | None, Query(max_length=36)] = None,
    mode: Annotated[Mode, Query()] = "explicit",
) -> Response:
    app.get_revision(db, revision_id)
    if kind == "lines":
        sheets = [bx.lines_sheet(db, revision_id)]
    elif kind == "consolidated":
        sheets = [bx.consolidated_sheet(db, revision_id, _need(root), vehicles)]
    elif kind == "hierarchy":
        sheets = [bx.hierarchy_sheet(db, revision_id, _need(root))]
    elif kind == "issues":
        sheets = [bx.issues_sheet(db, revision_id, mode)]
    elif kind == "compare":
        sheets = [bx.compare_sheet(db, revision_id, _need(other_revision))]
    else:
        raise DomainError("Esta exportação precisa de parâmetros específicos (use a tela do BOM).")
    body = (
        to_csv_bytes(sheets[0].headers, sheets[0].rows) if fmt == "csv" else to_xlsx_bytes(sheets)
    )
    media = (
        "text/csv; charset=utf-8"
        if fmt == "csv"
        else ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )
    name = f"bom-{kind}.{fmt}"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _need(value: str | None) -> str:
    if not value:
        raise DomainError("Parâmetro obrigatório ausente para esta exportação.")
    return value


class KitImportIn(BaseModel):
    name: str = Field(default="", max_length=160)
    dataset_id: str = Field(min_length=1, max_length=36)
    mapping: dict[str, str] = Field(default_factory=dict)


@router.post("/structures/{structure_id}/kits/import/preview")
def kit_import_preview(
    structure_id: str, payload: KitImportIn, user: CurrentUser, db: DbDep
) -> dict[str, Any]:
    """Prévia da lista de kit (código, quantidade, unidade, descrição). Não grava nada."""
    app.get_structure(db, structure_id)
    return app.kit_rows_from_dataset(
        db, structure_id, _dataset(db, payload.dataset_id), payload.mapping
    )


@router.post("/structures/{structure_id}/kits/import", status_code=201)
def kit_import(
    structure_id: str, payload: KitImportIn, request: Request, user: CurrentUser, db: DbDep
) -> dict[str, Any]:
    """Cria o kit a partir da tabela, recalculada no servidor, nunca do navegador."""
    structure = app.get_structure(db, structure_id)
    kit = app.add_kit_from_dataset(
        db, structure, payload.name, _dataset(db, payload.dataset_id), payload.mapping
    )
    record_event(
        db,
        actor=user.email,
        action="bom.kit.import",
        resource=f"bom:{structure.id}",
        result="ok",
        correlation_id=_correlation(request),
        details={"kit": kit.id},
    )
    db.commit()
    return {"id": kit.id, "name": kit.name, "parts": kit.parts}
