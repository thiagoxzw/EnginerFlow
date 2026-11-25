"""Medição da Fase 2B.2 em PostgreSQL com dados SINTÉTICOS (100 mil e 500 mil linhas).

Uso (somente em banco de teste; o script APAGA e recria o schema do banco indicado):
    ENGIFLOW_BENCH_DATABASE_URL=postgresql+psycopg://... \
        uv run python scripts/bench_2b2_postgres.py --rows 100000

Mede tempo (perf_counter) e pico de memória Python (tracemalloc) de cada caso. O pico cobre
objetos criados pelo código da aplicação, não o processo inteiro. Os resultados são de UMA
máquina e UM tamanho de amostra: não são garantias de capacidade.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import time
import tracemalloc
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from engiflow_api.application import data_studio as ds
from engiflow_api.application import table_query, versioning
from engiflow_api.domain.query import FilterIn, TableQuery
from engiflow_api.infrastructure.models import Base, Dataset, DatasetVersion
from engiflow_api.infrastructure.readers import ImportLimits


def make_csv(path: Path, rows: int) -> None:
    """Dados sintéticos com zeros à esquerda, decimais com vírgula e termos repetidos."""
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("SYN-Código;SYN-Descrição;Unidade;Qtd\n")
        for i in range(1, rows + 1):
            fh.write(f"{i:08d};SYN Parafuso M{i % 40} sextavado item {i};UN;{i % 9},5\n")


def timed(label: str, action: Callable[[], Any]) -> dict[str, Any]:
    """Tempo sem tracemalloc; pico de memória em execução separada (tracemalloc é lento)."""
    started = time.perf_counter()
    result = action()
    elapsed = time.perf_counter() - started

    tracemalloc.start()
    try:
        action()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "caso": label,
        "segundos": round(elapsed, 3),
        "pico_MB": round(peak / 1e6, 1),
        "resultado": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    args = parser.parse_args()
    url = os.environ.get("ENGIFLOW_BENCH_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        print(
            "Defina ENGIFLOW_BENCH_DATABASE_URL com um banco PostgreSQL de teste.", file=sys.stderr
        )
        return 2

    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    limits = ImportLimits(max_rows=2_000_000)
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        storage = base / "originals"
        storage.mkdir()
        source = base / "syn.csv"
        make_csv(source, args.rows)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        print(f"amostra sintética: {args.rows} linhas; {source.stat().st_size / 1e6:.1f} MB CSV")

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

        # Importação real (grava em PostgreSQL). Uma única medição: é a mais cara.
        started = time.perf_counter()
        dataset_id = do_import()
        results.append(
            {
                "caso": "importação CSV (PostgreSQL)",
                "segundos": round(time.perf_counter() - started, 2),
            }
        )

        def with_db(action: Callable[[DbSession, Dataset], Any]) -> Callable[[], Any]:
            def run() -> Any:
                with factory() as db:
                    dataset = db.get(Dataset, dataset_id)
                    assert dataset is not None
                    return action(db, dataset)

            return run

        def page_no_filter(db: DbSession, dataset: Dataset) -> int:
            query = TableQuery()
            total, rows = table_query.query_page(db, dataset, query, offset=0, limit=100)
            return total + len(rows)

        def filtered(db: DbSession, dataset: Dataset) -> int:
            flt = FilterIn(column="Qtd", op="gt", value="4,5")
            total, rows = table_query.query_page(
                db, dataset, TableQuery(filters=[flt]), offset=0, limit=100
            )
            return total + len(rows)

        def search(db: DbSession, dataset: Dataset) -> int:
            total, rows = table_query.query_page(
                db, dataset, TableQuery(search="m7 sextavado"), offset=0, limit=100
            )
            return total + len(rows)

        def sorted_numeric(db: DbSession, dataset: Dataset) -> int:
            total, rows = table_query.query_page(
                db, dataset, TableQuery(sort_column="Qtd", descending=True), offset=0, limit=100
            )
            return total + len(rows)

        results.append(timed("consulta sem filtro (página 100)", with_db(page_no_filter)))
        results.append(timed("filtro numérico (Qtd > 4,5)", with_db(filtered)))
        results.append(timed("pesquisa global (sem acento)", with_db(search)))
        results.append(timed("ordenação numérica (todas as linhas)", with_db(sorted_numeric)))

        def replace_preview_apply(db: DbSession, dataset: Dataset) -> int:
            state = versioning.current_state(db, dataset)
            preview = versioning.create_preview(
                db,
                dataset,
                code="replace_text",
                raw_params={"columns": ["SYN-Descrição"], "find": "Parafuso", "replace": "Porca"},
                base_version_id=state.data_version_id,
                base_metadata_version_id=state.metadata_version_id,
                actor="bench@example.com",
                correlation_id="bench",
            )
            db.commit()
            outcome = versioning.apply_preview(
                db,
                dataset,
                preview_id=preview.id,
                base_version_id=state.data_version_id,
                base_metadata_version_id=state.metadata_version_id,
                idempotency_key=None,
                actor="bench@example.com",
                correlation_id="bench",
            )
            db.commit()
            return outcome.operation.rows_affected

        results.append(
            timed("substituição em lote (prévia + aplicação)", with_db(replace_preview_apply))
        )

        def undo_once(db: DbSession, dataset: Dataset) -> str:
            state = versioning.current_state(db, dataset)
            target = versioning.undo(
                db,
                dataset,
                base_version_id=state.data_version_id,
                base_metadata_version_id=state.metadata_version_id,
                actor="bench@example.com",
                correlation_id="bench",
            )
            db.commit()
            version = db.get(DatasetVersion, target.data_version_id)
            return version.id if version else ""

        results.append(timed("desfazer (move ponteiros)", with_db(undo_once)))

    engine.dispose()
    print()
    print(f"{'caso':<42}{'segundos':>10}{'pico_MB':>10}")
    for row in results:
        print(f"{row['caso']!s:<42}{row['segundos']!s:>10}{row.get('pico_MB', '-')!s:>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
