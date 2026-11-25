"""Medição da Fase 2B.3 em PostgreSQL com dados SINTÉTICOS.

Cobre Super-PROCV, junção, comparação e agregação.

Uso (somente em banco de teste: o script APAGA o schema public do banco indicado):
    ENGIFLOW_BENCH_DATABASE_URL=postgresql+psycopg://... \
        uv run python scripts/bench_2b3_postgres.py --rows 100000

Dados: tabela de consulta com N linhas e tabela de busca com N linhas. Metade das chaves casa,
há chaves repetidas nos dois lados (correspondências múltiplas) e algumas chaves vazias.
Cada operação é medida duas vezes: uma para o tempo (sem tracemalloc) e outra para o pico de
memória Python (tracemalloc). O pico cobre objetos criados pelo código da aplicação, não o
processo inteiro. Resultados são de UMA máquina e UM tamanho de amostra: não são garantias.
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

from engiflow_api.application import crossing as cx
from engiflow_api.application import data_studio as ds
from engiflow_api.domain import lookup as lk
from engiflow_api.infrastructure.models import Base, Dataset
from engiflow_api.infrastructure.readers import ImportLimits


def make_left(path: Path, rows: int) -> None:
    """Consulta: zeros à esquerda; chave vazia a cada 50 linhas; repetida a cada 97."""
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("SYN-Código;SYN-Unidade;SYN-Qtd\n")
        for i in range(1, rows + 1):
            code = "" if i % 50 == 0 else f"{(i if i % 97 else i - 1):08d}"
            fh.write(f"{code};UN;{i % 9},5\n")


def make_right(path: Path, rows: int) -> None:
    """Busca: metade sobrepõe a consulta; a cada 80 linhas uma chave repetida; preço com vírgula."""
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("SYN-Código;SYN-Unidade;SYN-Preço\n")
        for i in range(1, rows + 1):
            base = rows // 2 + i if i % 80 else rows // 2 + i - 1
            fh.write(f"{base:08d};UN;{(i % 1000)},25\n")


def measure(label: str, action: Callable[[], Any]) -> dict[str, Any]:
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
    return [
        f"Sistema: {platform.platform()}",
        f"Python: {platform.python_version()}",
        f"PostgreSQL: {pg_version}",
        f"CPUs lógicas: {os.cpu_count()}",
    ]


def reset_schema(engine: Any) -> None:
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
    print(f"amostra sintética: {args.rows} linhas por tabela")
    for line in environment(engine):
        print(line)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        storage = base / "originals"
        storage.mkdir()
        files = {"left": base / "consulta.csv", "right": base / "busca.csv"}
        make_left(files["left"], args.rows)
        make_right(files["right"], args.rows)

        def do_import(path: Path) -> str:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            temp = storage / f".tmp-{uuid.uuid4().hex}"
            temp.write_bytes(path.read_bytes())
            with factory() as db:
                result = ds.import_upload(
                    db,
                    actor="bench@example.com",
                    filename=path.name,
                    temp_path=temp,
                    digest=digest,
                    sheet=None,
                    limits=limits,
                    storage_dir=storage,
                    correlation_id="bench",
                )
                return result.dataset.id

        started = time.perf_counter()
        left_id = do_import(files["left"])
        right_id = do_import(files["right"])
        results.append(
            {
                "caso": "importação das duas tabelas",
                "segundos": round(time.perf_counter() - started, 3),
                "pico_MB": "n/a",
            }
        )

        def with_pair(action: Callable[[DbSession, Dataset, Dataset], Any]) -> Callable[[], Any]:
            def run() -> Any:
                with factory() as db:
                    left = db.get(Dataset, left_id)
                    right = db.get(Dataset, right_id)
                    assert left is not None and right is not None
                    return action(db, left, right)

            return run

        keys_left = ("SYN-Código",)
        keys_right = ("SYN-Código",)

        def lookup_preview(db: DbSession, left: Dataset, right: Dataset) -> None:
            spec = cx.LookupSpec(
                left_keys=keys_left,
                right_keys=keys_right,
                return_columns=("SYN-Preço",),
                policy=lk.LookupPolicy(duplicates="first", unmatched="keep_empty"),
            )
            cx.run_lookup(db, left, right, spec, max_output_rows=2_000_000)

        def join_preview(db: DbSession, left: Dataset, right: Dataset) -> None:
            cx.run_join(db, left, right, keys_left, keys_right, "left")

        def compare_preview(db: DbSession, left: Dataset, right: Dataset) -> None:
            cx.run_comparison(
                db, left, right, cx.ComparisonSpec(left_keys=keys_left, right_keys=keys_right)
            )

        def aggregate_preview(db: DbSession, left: Dataset, _right: Dataset) -> None:
            cx.run_aggregate(
                db,
                left,
                cx.AggregateSpec(group_by=("SYN-Unidade",), measures=(("SYN-Qtd", "sum"),)),
            )

        def lookup_derive(db: DbSession, left: Dataset, right: Dataset) -> None:
            spec = cx.LookupSpec(
                left_keys=keys_left,
                right_keys=keys_right,
                return_columns=("SYN-Preço",),
                policy=lk.LookupPolicy(duplicates="first", unmatched="keep_empty"),
            )
            cx.create_derived_lookup(
                db, left, right, spec, actor="bench@example.com", correlation_id="bench"
            )
            db.commit()

        for label, action in [
            ("Super-PROCV: prévia (consulta × busca)", lookup_preview),
            ("junção esquerda: prévia (cardinalidade e estimativa)", join_preview),
            ("comparação por chave: contagens", compare_preview),
            ("agregação: soma por unidade (decimal)", aggregate_preview),
        ]:
            results.append(measure(label, with_pair(action)))

        derive_started = time.perf_counter()
        with_pair(lookup_derive)()
        results.append(
            {
                "caso": "Super-PROCV: criação de tabela derivada (uma vez)",
                "segundos": round(time.perf_counter() - derive_started, 3),
                "pico_MB": "n/a",
            }
        )

    print()
    print(f"{'caso':<56}{'segundos':>10}{'pico_MB':>10}")
    for row in results:
        print(f"{row['caso']!s:<56}{row['segundos']!s:>10}{row['pico_MB']!s:>10}")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
