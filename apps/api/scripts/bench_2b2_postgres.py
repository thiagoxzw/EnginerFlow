"""Medição da Fase 2B.2 em PostgreSQL com dados SINTÉTICOS (100 mil e 500 mil linhas).

Uso (somente em banco de teste: o script APAGA o schema public do banco indicado):
    ENGIFLOW_BENCH_DATABASE_URL=postgresql+psycopg://... \
        uv run python scripts/bench_2b2_postgres.py --rows 100000

Cada operação é medida duas vezes: uma para o tempo (sem tracemalloc, que é lento) e outra
para o pico de memória Python (tracemalloc). O pico cobre objetos criados pelo código da
aplicação, não o processo inteiro. Resultados são de UMA máquina e UM tamanho de amostra:
não são garantias de capacidade.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import sys
import tempfile
import time
import tracemalloc
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from engiflow_api.application import data_studio as ds
from engiflow_api.application import table_query, versioning
from engiflow_api.domain.query import FilterIn, TableQuery
from engiflow_api.infrastructure.models import Base, Dataset
from engiflow_api.infrastructure.readers import ImportLimits


def make_csv(path: Path, rows: int) -> None:
    """Dados sintéticos com zeros à esquerda, decimais com vírgula e termos repetidos."""
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("SYN-Código;SYN-Descrição;Unidade;Qtd\n")
        for i in range(1, rows + 1):
            fh.write(f"{i:08d};SYN Parafuso M{i % 40} sextavado item {i};UN;{i % 9},5\n")


def measure(label: str, action: Callable[[], Any]) -> dict[str, Any]:
    """Tempo (sem tracemalloc) e pico de memória Python (com tracemalloc), em duas execuções."""
    started = time.perf_counter()
    action()
    elapsed = time.perf_counter() - started
    tracemalloc.start()
    try:
        action()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"caso": label, "segundos": round(elapsed, 3), "pico_MB": round(peak / 1e6, 1)}


def environment(engine: Any) -> list[str]:
    with engine.connect() as conn:
        pg_version = conn.execute(text("SHOW server_version")).scalar_one()
    cpus = os.cpu_count()
    return [
        f"Sistema: {platform.platform()}",
        f"Python: {platform.python_version()}",
        f"PostgreSQL: {pg_version}",
        f"CPUs lógicas: {cpus}",
    ]


def table_bytes(engine: Any, table: str) -> int:
    with engine.connect() as conn:
        size: int = conn.execute(
            text("SELECT pg_total_relation_size(CAST(:t AS regclass))"), {"t": table}
        ).scalar_one()
    return size


def reset_schema(engine: Any) -> None:
    """Recria o schema inteiro: drop_all falha com a FK circular datasets <-> versões."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(engine)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    args = parser.parse_args()
    url = os.environ.get("ENGIFLOW_BENCH_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        print("Defina ENGIFLOW_BENCH_DATABASE_URL com um PostgreSQL de teste.", file=sys.stderr)
        return 2

    engine = create_engine(url)
    reset_schema(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    limits = ImportLimits(max_rows=2_000_000)
    results: list[dict[str, Any]] = []
    print(f"amostra sintética: {args.rows} linhas")
    for line in environment(engine):
        print(line)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        storage = base / "originals"
        storage.mkdir()
        source = base / "syn.csv"
        make_csv(source, args.rows)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        print(f"arquivo CSV sintético: {source.stat().st_size / 1e6:.1f} MB")

        def do_import() -> str:
            temp = storage / f".tmp-{uuid.uuid4().hex}"
            temp.write_bytes(source.read_bytes())
            with factory() as db:
                result = ds.import_upload(
                    db,
                    actor="bench@example.com",
                    filename=source.name,
                    temp_path=temp,
                    digest=digest,
                    sheet=None,
                    limits=limits,
                    storage_dir=storage,
                    correlation_id="bench",
                )
                return result.dataset.id

        storage_before = table_bytes(engine, "dataset_version_rows")
        started = time.perf_counter()
        dataset_id = do_import()
        import_seconds = round(time.perf_counter() - started, 3)
        results.append({"caso": "importação CSV", "segundos": import_seconds, "pico_MB": "n/a"})
        storage_v1 = table_bytes(engine, "dataset_version_rows") - storage_before

        def with_db(action: Callable[[DbSession, Dataset], Any]) -> Callable[[], Any]:
            def run() -> Any:
                with factory() as db:
                    dataset = db.get(Dataset, dataset_id)
                    assert dataset is not None
                    return action(db, dataset)

            return run

        def filtered(db: DbSession, dataset: Dataset) -> None:
            flt = FilterIn(column="Qtd", op="gt", value="4,5")
            table_query.query_page(db, dataset, TableQuery(filters=[flt]), offset=0, limit=100)

        def search(db: DbSession, dataset: Dataset) -> None:
            table_query.query_page(
                db, dataset, TableQuery(search="m7 sextavado"), offset=0, limit=100
            )

        def sorted_numeric(db: DbSession, dataset: Dataset) -> None:
            table_query.query_page(
                db, dataset, TableQuery(sort_column="Qtd", descending=True), offset=0, limit=100
            )

        def select_by_filter(db: DbSession, dataset: Dataset) -> None:
            flt = FilterIn(column="Qtd", op="gt", value="4,5")
            table_query.matching_row_numbers(db, dataset, TableQuery(filters=[flt]), cap=args.rows)

        for label, action in [
            ("filtragem (Qtd > 4,5, página 100)", filtered),
            ("pesquisa global (sem acento)", search),
            ("ordenação numérica (todas as linhas)", sorted_numeric),
            ("seleção de linhas por filtro", select_by_filter),
        ]:
            results.append(measure(label, with_db(action)))

        replace_params = {
            "columns": ["SYN-Descrição"],
            "find": "Parafuso",
            "replace": "Porca",
        }
        preview_ids: dict[str, str] = {}

        def preview(db: DbSession, dataset: Dataset) -> None:
            state = versioning.current_state(db, dataset)
            created = versioning.create_preview(
                db,
                dataset,
                code="replace_text",
                raw_params=replace_params,
                base_version_id=state.data_version_id,
                base_metadata_version_id=state.metadata_version_id,
                actor="bench@example.com",
                correlation_id="bench",
            )
            db.commit()
            preview_ids["id"] = created.id

        results.append(measure("geração de prévia (substituição)", with_db(preview)))

        def apply_replace(db: DbSession, dataset: Dataset) -> None:
            state = versioning.current_state(db, dataset)
            # Nova prévia a cada execução: a prévia é consumida pela aplicação.
            created = versioning.create_preview(
                db,
                dataset,
                code="replace_text",
                raw_params=replace_params,
                base_version_id=state.data_version_id,
                base_metadata_version_id=state.metadata_version_id,
                actor="bench@example.com",
                correlation_id="bench",
            )
            db.commit()
            versioning.apply_preview(
                db,
                dataset,
                preview_id=created.id,
                base_version_id=state.data_version_id,
                base_metadata_version_id=state.metadata_version_id,
                idempotency_key=None,
                actor="bench@example.com",
                correlation_id="bench",
            )
            db.commit()

        storage_before_apply = table_bytes(engine, "dataset_version_rows")
        results.append(
            measure("aplicação de substituição (prévia + aplicação)", with_db(apply_replace))
        )
        storage_v2 = table_bytes(engine, "dataset_version_rows") - storage_before_apply

        def undo_once(db: DbSession, dataset: Dataset) -> None:
            state = versioning.current_state(db, dataset)
            versioning.undo(
                db,
                dataset,
                base_version_id=state.data_version_id,
                base_metadata_version_id=state.metadata_version_id,
                actor="bench@example.com",
                correlation_id="bench",
            )
            db.commit()

        results.append(measure("desfazer (move ponteiros)", with_db(undo_once)))

    print()
    print(f"{'caso':<48}{'segundos':>10}{'pico_MB':>10}")
    for row in results:
        print(f"{row['caso']!s:<48}{row['segundos']!s:>10}{row['pico_MB']!s:>10}")
    print()
    print(f"crescimento de armazenamento, versão 1 (importação): {storage_v1 / 1e6:.1f} MB")
    print(f"crescimento de armazenamento, nova versão por substituição: {storage_v2 / 1e6:.1f} MB")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
