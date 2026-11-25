"""Rotas do Data Studio (/api/v1/datasets)."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from engiflow_api.application.data_studio import (
    compare_datasets,
    dataset_rows_iter,
    find_duplicates,
    get_dataset,
    import_upload,
    rename_dataset,
    restore_dataset,
    set_mapping,
    soft_delete_dataset,
    sweep_stale_temp_files,
)
from engiflow_api.application.table_query import matching_row_numbers, query_page
from engiflow_api.core.config import get_settings
from engiflow_api.domain.errors import DomainError
from engiflow_api.domain.query import MAX_SEARCH, FilterIn, TableQuery
from engiflow_api.domain.tabular import CodeComparison, detect_header_index
from engiflow_api.infrastructure.exporters import Sheet, to_csv_bytes, to_xlsx_bytes
from engiflow_api.infrastructure.models import (
    CrossingRun,
    CrossingRunSource,
    Dataset,
    DatasetVersionRow,
)
from engiflow_api.infrastructure.readers import (
    ImportLimits,
    detect_kind_file,
    list_sheets_file,
    read_raw_head,
)
from engiflow_api.presentation.deps import CurrentUser, DbDep

router = APIRouter(prefix="/api/v1/datasets", tags=["data-studio"])

_PREVIEW_ROWS = 20
_INSPECT_ROWS = 15
_CHUNK = 1024 * 1024
_EXPORT_MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
Format = Literal["csv", "xlsx"]


class DatasetSummary(BaseModel):
    id: str
    name: str
    source_filename: str
    file_kind: str
    sheet_name: str | None
    columns: list[str]
    row_count: int
    mapping: dict[str, str]
    warnings: list[str]
    created_at: datetime
    source_kind: str = "import"
    derived_run_id: str | None = None


class DatasetDetail(DatasetSummary):
    preview: list[dict[str, Any]]


class ImportOut(BaseModel):
    created: bool
    dataset: DatasetSummary


class MappingIn(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class RowOut(BaseModel):
    row_number: int
    values: list[str | None]


class RowsOut(BaseModel):
    total: int
    offset: int
    limit: int
    columns: list[str]
    rows: list[RowOut]


class ExactGroupOut(BaseModel):
    key: str
    row_numbers: list[int]
    values: list[str]


class LeadingZeroOut(BaseModel):
    key_a: str
    key_b: str


class SimilarOut(BaseModel):
    row_a: int
    row_b: int
    value_a: str
    value_b: str
    score: float
    shared_tokens: list[str]
    reason: str
    spec_match: bool


class DuplicatesOut(BaseModel):
    exact_codes: list[ExactGroupOut]
    leading_zero_suspicions: list[LeadingZeroOut]
    similar_descriptions: list[SimilarOut]
    note: str


class CompareIn(BaseModel):
    left_id: str
    right_id: str


class CompareOut(BaseModel):
    """Listas completas (sem corte): nenhum candidato é omitido na resposta."""

    only_left_count: int
    only_right_count: int
    in_both_count: int
    only_left: list[str]
    only_right: list[str]
    leading_zero_candidates: list[dict[str, str]]
    note: str


def _summary(dataset: Dataset) -> DatasetSummary:
    return DatasetSummary(
        id=dataset.id,
        name=dataset.name,
        source_filename=dataset.source_filename,
        file_kind=dataset.file_kind,
        sheet_name=dataset.sheet_name,
        columns=list(dataset.columns),
        row_count=dataset.row_count,
        mapping=dict(dataset.mapping),
        warnings=list(dataset.warnings),
        created_at=dataset.created_at,
        source_kind=dataset.source_kind,
        derived_run_id=dataset.derived_run_id,
    )


def _correlation(request: Request) -> str | None:
    value: str | None = getattr(request.state, "correlation_id", None)
    return value


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return (cleaned or "resultado")[:60]


def _download(content: bytes, fmt: Format, base: str) -> Response:
    filename = f"{_safe_filename(base)}.{fmt}"
    return Response(
        content=content,
        media_type=_EXPORT_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", status_code=201, response_model=ImportOut)
def upload(
    file: UploadFile,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbDep,
    sheet: Annotated[str | None, Form()] = None,
) -> ImportOut:
    """Recebe o arquivo em streaming: nunca carrega o upload inteiro na memória."""
    settings = get_settings()
    limits = ImportLimits(
        max_upload_bytes=settings.max_upload_mb * 1024 * 1024, max_rows=settings.max_rows
    )
    storage = Path(settings.data_dir) / "originals"
    storage.mkdir(parents=True, exist_ok=True)
    sweep_stale_temp_files(storage)
    temp_path = storage / f".tmp-{uuid.uuid4().hex}"
    digest = hashlib.sha256()
    size = 0
    try:
        with temp_path.open("wb") as out:
            while chunk := file.file.read(_CHUNK):
                size += len(chunk)
                if size > limits.max_upload_bytes:
                    raise DomainError(f"Arquivo excede o limite de {settings.max_upload_mb} MB.")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise DomainError("Arquivo vazio.")
        result = import_upload(
            db,
            actor=user.email,
            filename=file.filename or "tabela",
            temp_path=temp_path,
            digest=digest.hexdigest(),
            sheet=sheet or None,
            limits=limits,
            storage_dir=storage,
            correlation_id=_correlation(request),
        )
    finally:
        temp_path.unlink(missing_ok=True)
    if not result.created:
        response.status_code = 200
    return ImportOut(created=result.created, dataset=_summary(result.dataset))


@router.get("", response_model=list[DatasetSummary])
def list_datasets(
    user: CurrentUser,
    db: DbDep,
    deleted: Annotated[bool, Query()] = False,
) -> list[DatasetSummary]:
    """Tabelas ativas por padrão; com `deleted=true`, as excluídas logicamente."""
    condition = Dataset.deleted_at.is_not(None) if deleted else Dataset.deleted_at.is_(None)
    rows = db.scalars(
        select(Dataset).where(condition).order_by(Dataset.created_at.desc()).limit(200)
    ).all()
    return [_summary(d) for d in rows]


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DeleteIn(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=255)


@router.patch("/{dataset_id}", response_model=DatasetSummary)
def rename(
    dataset_id: str, payload: RenameIn, request: Request, user: CurrentUser, db: DbDep
) -> DatasetSummary:
    dataset = get_dataset(db, dataset_id)
    rename_dataset(
        db, dataset, payload.name, actor=user.email, correlation_id=_correlation(request)
    )
    db.commit()
    return _summary(dataset)


@router.delete("/{dataset_id}", response_model=DatasetSummary)
def delete(
    dataset_id: str, payload: DeleteIn, request: Request, user: CurrentUser, db: DbDep
) -> DatasetSummary:
    """Exclusão lógica: exige o nome exato. A tabela pode ser restaurada."""
    dataset = get_dataset(db, dataset_id)
    soft_delete_dataset(
        db,
        dataset,
        payload.confirm_name,
        actor=user.email,
        correlation_id=_correlation(request),
    )
    db.commit()
    return _summary(dataset)


@router.post("/{dataset_id}/restore", response_model=DatasetSummary)
def restore(dataset_id: str, request: Request, user: CurrentUser, db: DbDep) -> DatasetSummary:
    dataset = get_dataset(db, dataset_id, include_deleted=True)
    restore_dataset(db, dataset, actor=user.email, correlation_id=_correlation(request))
    db.commit()
    return _summary(dataset)


@router.get("/{dataset_id}", response_model=DatasetDetail)
def detail(dataset_id: str, user: CurrentUser, db: DbDep) -> DatasetDetail:
    dataset = get_dataset(db, dataset_id)
    preview_rows = db.execute(
        select(DatasetVersionRow.values)
        .where(DatasetVersionRow.version_id == dataset.current_version_id)
        .order_by(DatasetVersionRow.row_number)
        .limit(_PREVIEW_ROWS)
    ).all()
    preview = [dict(zip(dataset.columns, values[0], strict=False)) for values in preview_rows]
    base = _summary(dataset).model_dump()
    return DatasetDetail(**base, preview=preview)


class LineageSourceOut(BaseModel):
    role: str
    dataset_id: str
    dataset_name: str
    version_id: str
    metadata_version_id: str
    # Origem ainda existe e não está excluída logicamente. A derivada não muda em nenhum caso.
    still_active: bool


class LineageOut(BaseModel):
    dataset_id: str
    run_id: str
    operation: str
    operation_version: int
    params: dict[str, Any]
    policy: dict[str, Any]
    counts: dict[str, Any]
    params_sha256: str
    result_sha256: str
    row_count: int
    actor: str
    created_at: datetime
    sources: list[LineageSourceOut]


_OPERATION_NAMES = {
    "lookup": "Super-PROCV",
    "join": "Junção",
    "aggregate": "Agregação",
    "compare": "Comparação por chave",
    "formula": "Fórmula",
}


@router.get("/{dataset_id}/lineage", response_model=LineageOut)
def lineage(dataset_id: str, user: CurrentUser, db: DbDep) -> LineageOut:
    """Rastreabilidade de uma tabela derivada: operação, parâmetros, origens, contagens e hash."""
    dataset = get_dataset(db, dataset_id)
    if not dataset.derived_run_id:
        raise DomainError("Esta tabela não foi derivada de um cruzamento.")
    run = db.get(CrossingRun, dataset.derived_run_id)
    if run is None:
        raise DomainError("Execução de origem não encontrada.")
    sources = db.scalars(
        select(CrossingRunSource)
        .where(CrossingRunSource.run_id == run.id)
        .order_by(CrossingRunSource.role)
    ).all()
    active = {
        d.id: d.deleted_at is None
        for d in db.scalars(select(Dataset).where(Dataset.id.in_([s.dataset_id for s in sources])))
    }
    return LineageOut(
        dataset_id=dataset.id,
        run_id=run.id,
        operation=_OPERATION_NAMES.get(run.kind, run.kind),
        operation_version=run.operation_version,
        params=dict(run.params),
        policy=dict(run.policy),
        counts=dict(run.counts),
        params_sha256=run.params_sha256,
        result_sha256=run.result_sha256,
        row_count=run.row_count,
        actor=run.actor,
        created_at=run.created_at,
        sources=[
            LineageSourceOut(
                role=s.role,
                dataset_id=s.dataset_id,
                dataset_name=s.dataset_name,
                version_id=s.version_id,
                metadata_version_id=s.metadata_version_id,
                still_active=active.get(s.dataset_id, False),
            )
            for s in sources
        ],
    )


def _parse_filters(raw: str | None) -> list[FilterIn]:
    """Filtros chegam como JSON na query string. Qualquer formato inválido vira erro de regra."""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DomainError("Filtros em formato JSON inválido.") from exc
    if not isinstance(items, list):
        raise DomainError("Filtros devem ser uma lista.")
    try:
        return [FilterIn.model_validate(item) for item in items]
    except ValidationError as exc:
        raise DomainError("Filtro inválido.") from exc


@router.get("/{dataset_id}/rows", response_model=RowsOut)
def rows(
    dataset_id: str,
    user: CurrentUser,
    db: DbDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    q: Annotated[str, Query(max_length=MAX_SEARCH)] = "",
    filters: Annotated[str | None, Query(max_length=8000)] = None,
    sort: Annotated[str | None, Query(max_length=255)] = None,
    dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> RowsOut:
    """Linhas da versão atual. Sem filtro/pesquisa/ordenação usa a leitura direta por página."""
    dataset = get_dataset(db, dataset_id)
    query = TableQuery(
        filters=_parse_filters(filters),
        search=q,
        sort_column=sort,
        descending=dir == "desc",
    )
    if not query.is_plain():
        total, page_rows = query_page(db, dataset, query, offset=offset, limit=limit)
        return RowsOut(
            total=total,
            offset=offset,
            limit=limit,
            columns=list(dataset.columns),
            rows=[RowOut(row_number=n, values=list(v)) for n, v in page_rows],
        )
    total = (
        db.scalar(
            select(func.count())
            .select_from(DatasetVersionRow)
            .where(DatasetVersionRow.version_id == dataset.current_version_id)
        )
        or 0
    )
    page = db.execute(
        select(DatasetVersionRow.row_number, DatasetVersionRow.values)
        .where(DatasetVersionRow.version_id == dataset.current_version_id)
        .order_by(DatasetVersionRow.row_number)
        .offset(offset)
        .limit(limit)
    ).all()
    return RowsOut(
        total=int(total),
        offset=offset,
        limit=limit,
        columns=list(dataset.columns),
        rows=[RowOut(row_number=n, values=list(v)) for n, v in page],
    )


class SelectionIn(BaseModel):
    q: str = Field(default="", max_length=MAX_SEARCH)
    filters: list[FilterIn] = Field(default_factory=list, max_length=20)


class SelectionOut(BaseModel):
    count: int
    row_numbers: list[int]


@router.post("/{dataset_id}/rows/selection", response_model=SelectionOut)
def select_rows(
    dataset_id: str, payload: SelectionIn, user: CurrentUser, db: DbDep
) -> SelectionOut:
    """Números das linhas que casam com filtros e pesquisa (para ações em lote)."""
    dataset = get_dataset(db, dataset_id)
    query = TableQuery(filters=list(payload.filters), search=payload.q)
    numbers = matching_row_numbers(db, dataset, query)
    return SelectionOut(count=len(numbers), row_numbers=numbers)


@router.put("/{dataset_id}/mapping", response_model=DatasetSummary)
def mapping(
    dataset_id: str, payload: MappingIn, request: Request, user: CurrentUser, db: DbDep
) -> DatasetSummary:
    dataset = get_dataset(db, dataset_id)
    correlation_id = _correlation(request)
    set_mapping(db, dataset, payload.mapping, actor=user.email, correlation_id=correlation_id)
    db.commit()
    return _summary(dataset)


def _duplicates_report(
    db: DbSession, dataset: Dataset, threshold: float, descriptions: bool
) -> DuplicatesOut:
    report = find_duplicates(db, dataset, threshold=threshold, check_descriptions=descriptions)
    return DuplicatesOut(
        exact_codes=[
            ExactGroupOut(key=g.key, row_numbers=g.row_numbers, values=g.values)
            for g in report.exact_codes
        ],
        leading_zero_suspicions=[
            LeadingZeroOut(key_a=s.key_a, key_b=s.key_b) for s in report.leading_zero_suspicions
        ],
        similar_descriptions=[
            SimilarOut(
                row_a=p.row_a,
                row_b=p.row_b,
                value_a=p.value_a,
                value_b=p.value_b,
                score=p.score,
                shared_tokens=p.shared_tokens,
                reason=p.reason,
                spec_match=p.spec_match,
            )
            for p in report.similar_descriptions
        ],
        note=(
            "Duplicatas e semelhanças são sugestões para revisão humana. Nenhum registro é "
            "removido nem considerado equivalente automaticamente."
        ),
    )


@router.get("/{dataset_id}/duplicates", response_model=DuplicatesOut)
def duplicates(
    dataset_id: str,
    user: CurrentUser,
    db: DbDep,
    threshold: Annotated[float, Query(ge=0.5, le=1.0)] = 0.85,
    descriptions: Annotated[bool, Query()] = True,
) -> DuplicatesOut:
    dataset = get_dataset(db, dataset_id)
    return _duplicates_report(db, dataset, threshold, descriptions)


def _compare_result(db: DbSession, payload: CompareIn) -> tuple[Dataset, Dataset, CodeComparison]:
    left = get_dataset(db, payload.left_id)
    right = get_dataset(db, payload.right_id)
    for dataset in (left, right):
        if "code" not in dataset.mapping:
            raise DomainError(
                f"A tabela '{dataset.name}' não tem o campo 'code' mapeado. "
                "Mapeie antes de comparar."
            )
    return left, right, compare_datasets(db, left, right)


@router.post("/compare", response_model=CompareOut)
def compare(payload: CompareIn, user: CurrentUser, db: DbDep) -> CompareOut:
    _, _, result = _compare_result(db, payload)
    return CompareOut(
        only_left_count=len(result.only_left),
        only_right_count=len(result.only_right),
        in_both_count=len(result.in_both),
        only_left=result.only_left,
        only_right=result.only_right,
        leading_zero_candidates=[
            {"esquerda": a, "direita": b} for a, b in result.leading_zero_candidates
        ],
        note=(
            "Comparação por chave de código (sem diferença de caixa, zeros preservados). "
            "Candidatos por zeros à esquerda exigem confirmação humana."
        ),
    )


# ---------- exportação ----------


@router.get("/{dataset_id}/export")
def export_dataset(
    dataset_id: str,
    user: CurrentUser,
    db: DbDep,
    fmt: Annotated[Format, Query(alias="format")] = "csv",
) -> Response:
    dataset = get_dataset(db, dataset_id)
    rows_data = [values for _, values in dataset_rows_iter(db, dataset)]
    if fmt == "csv":
        content = to_csv_bytes(dataset.columns, rows_data)
    else:
        content = to_xlsx_bytes([Sheet("Dados", dataset.columns, rows_data)])
    return _download(content, fmt, f"{dataset.name}_dados")


@router.get("/{dataset_id}/duplicates/export")
def export_duplicates(
    dataset_id: str,
    user: CurrentUser,
    db: DbDep,
    fmt: Annotated[Format, Query(alias="format")] = "csv",
    threshold: Annotated[float, Query(ge=0.5, le=1.0)] = 0.85,
    descriptions: Annotated[bool, Query()] = True,
) -> Response:
    dataset = get_dataset(db, dataset_id)
    report = _duplicates_report(db, dataset, threshold, descriptions)
    exact_rows = [
        [g.key, " ".join(str(n) for n in g.row_numbers), " | ".join(g.values)]
        for g in report.exact_codes
    ]
    zero_rows = [[s.key_a, s.key_b] for s in report.leading_zero_suspicions]
    similar_rows = [
        [
            str(p.row_a),
            str(p.row_b),
            p.value_a,
            p.value_b,
            f"{p.score:.4f}".replace(".", ","),
            ", ".join(p.shared_tokens),
            p.reason,
        ]
        for p in report.similar_descriptions
    ]
    if fmt == "xlsx":
        content = to_xlsx_bytes(
            [
                Sheet("Codigos_repetidos", ["Código", "Linhas", "Valores"], exact_rows),
                Sheet("Zeros_a_esquerda", ["Código A", "Código B"], zero_rows),
                Sheet(
                    "Semelhantes",
                    [
                        "Linha A",
                        "Linha B",
                        "Descrição A",
                        "Descrição B",
                        "Score",
                        "Termos",
                        "Motivo",
                    ],
                    similar_rows,
                ),
            ]
        )
    else:
        unified: list[list[str]] = []
        unified += [["codigo_repetido", r[1], "", r[0], "", "", "", "", r[2]] for r in exact_rows]
        unified += [
            ["zero_a_esquerda", "", "", r[0], r[1], "", "", "", "revisar"] for r in zero_rows
        ]
        unified += [
            ["descricao_semelhante", r[0], r[1], "", "", r[2], r[3], r[4], f"{r[5]} | {r[6]}"]
            for r in similar_rows
        ]
        content = to_csv_bytes(
            [
                "tipo",
                "linha_a",
                "linha_b",
                "codigo_a",
                "codigo_b",
                "descricao_a",
                "descricao_b",
                "score",
                "evidencia",
            ],
            unified,
        )
    return _download(content, fmt, f"{dataset.name}_duplicatas")


@router.post("/compare/export")
def export_compare(
    payload: CompareIn,
    user: CurrentUser,
    db: DbDep,
    fmt: Annotated[Format, Query(alias="format")] = "csv",
) -> Response:
    left, right, result = _compare_result(db, payload)
    only_left = [[c] for c in result.only_left]
    only_right = [[c] for c in result.only_right]
    in_both = [[c] for c in result.in_both]
    candidates = [[a, b] for a, b in result.leading_zero_candidates]
    if fmt == "xlsx":
        content = to_xlsx_bytes(
            [
                Sheet(f"Somente_{left.name}"[:31], ["Código"], only_left),
                Sheet(f"Somente_{right.name}"[:31], ["Código"], only_right),
                Sheet("Em_ambas", ["Código"], in_both),
                Sheet("Candidatos_zeros", ["Código A", "Código B"], candidates),
            ]
        )
    else:
        unified: list[list[str]] = []
        unified += [["somente_A", c[0], ""] for c in only_left]
        unified += [["somente_B", "", c[0]] for c in only_right]
        unified += [["em_ambas", c[0], c[0]] for c in in_both]
        unified += [["candidato_zeros", c[0], c[1]] for c in candidates]
        content = to_csv_bytes(["tipo", "codigo_a", "codigo_b"], unified)
    return _download(content, fmt, f"comparacao_{left.name}_x_{right.name}")


class RawRowOut(BaseModel):
    row_number: int
    values: list[str | None]


class InspectOut(BaseModel):
    kind: str
    sheets: list[str]
    sheet: str | None
    header_row: int | None
    columns: list[str]
    preview: list[RawRowOut]
    warnings: list[str]


@router.post("/inspect", response_model=InspectOut)
def inspect_upload(
    file: UploadFile,
    user: CurrentUser,
    sheet: Annotated[str | None, Form()] = None,
) -> InspectOut:
    """Lê o arquivo sem importar: abas, cabeçalho detectado e prévia. Nada é gravado no banco.

    O arquivo é gravado num temporário da pasta de armazenamento e removido ao final.
    """
    settings = get_settings()
    limits = ImportLimits(
        max_upload_bytes=settings.max_upload_mb * 1024 * 1024, max_rows=settings.max_rows
    )
    storage = Path(settings.data_dir) / "originals"
    storage.mkdir(parents=True, exist_ok=True)
    sweep_stale_temp_files(storage)
    temp_path = storage / f".tmp-inspect-{uuid.uuid4().hex}"
    size = 0
    try:
        with temp_path.open("wb") as out:
            while chunk := file.file.read(_CHUNK):
                size += len(chunk)
                if size > limits.max_upload_bytes:
                    raise DomainError(f"Arquivo excede o limite de {settings.max_upload_mb} MB.")
                out.write(chunk)
        if size == 0:
            raise DomainError("Arquivo vazio.")
        kind = detect_kind_file(temp_path)
        sheets: list[str] = []
        chosen: str | None = None
        if kind == "xlsx":
            sheets = list_sheets_file(temp_path, limits)
            if not sheets:
                raise DomainError("Planilha sem abas.")
            chosen = sheet or sheets[0]
            if chosen not in sheets:
                raise DomainError(f"Aba '{chosen}' não existe. Abas: {', '.join(sheets)}.")
        raw = read_raw_head(temp_path, kind, chosen, limits, _INSPECT_ROWS)
    finally:
        temp_path.unlink(missing_ok=True)

    warnings: list[str] = []
    header_row: int | None = None
    columns: list[str] = []
    if raw:
        header_index = detect_header_index([[c or "" for c in values] for _, values in raw])
        header_row = raw[header_index][0]
        columns = [c or "" for c in raw[header_index][1]]
        names = [c.strip().casefold() for c in columns if c and c.strip()]
        if len(names) != len(set(names)):
            warnings.append("Há nomes de coluna repetidos; eles receberão sufixos ao importar.")
        if any(not c.strip() for c in columns):
            warnings.append("Há colunas sem nome no cabeçalho detectado.")
    else:
        warnings.append("A aba está vazia.")
    return InspectOut(
        kind=kind,
        sheets=sheets,
        sheet=chosen,
        header_row=header_row,
        columns=columns,
        preview=[RawRowOut(row_number=n, values=v) for n, v in raw],
        warnings=warnings,
    )
