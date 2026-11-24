"""Medição de tempo e memória do Data Studio com dados SINTÉTICOS.

Uso (manual, não roda no CI):
    uv run python scripts/bench_data_studio.py --rows 20000 --old-commit c1a96bf

Mede o pico de memória Python (tracemalloc), que cobre objetos criados pelo código da aplicação.
Não cobre o consumo do processo inteiro (interpretador, SQLite, bibliotecas nativas).
Resultados são de UMA máquina e UM tamanho de amostra: não são garantias de capacidade.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
import time
import tracemalloc
import types
import uuid
from collections.abc import Callable
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engiflow_api.application import data_studio as ds
from engiflow_api.infrastructure.models import Base
from engiflow_api.infrastructure.readers import ImportLimits, open_csv


def make_csv(path: Path, rows: int) -> None:
    lines = ["SYN-Código;SYN-Descrição;Unidade;Qtd"]
    for i in range(1, rows + 1):
        # Códigos com zeros à esquerda e descrições com termos repetidos (dados sintéticos).
        lines.append(f"{i:08d};SYN Parafuso M{i % 40} sextavado item {i};UN;{i % 9}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_xlsx(path: Path, rows: int) -> None:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("SYN")
    ws.append(["SYN-Código", "SYN-Descrição", "Unidade", "Qtd"])
    for i in range(1, rows + 1):
        ws.append([f"{i:08d}", f"SYN Parafuso M{i % 40} sextavado item {i}", "UN", i % 9])
    wb.save(path)


def measure(label: str, make: Callable[[], Callable[[], object]]) -> dict[str, float | str]:
    """Tempo medido SEM tracemalloc (que deixa o Python mais lento); memória em rodada à parte.

    `make` devolve uma execução nova a cada chamada (ex.: banco novo), para que a segunda
    rodada não seja uma importação idempotente sem trabalho.
    """
    started = time.perf_counter()
    make()()
    elapsed = time.perf_counter() - started

    run = make()
    tracemalloc.start()
    try:
        run()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"caso": label, "segundos": round(elapsed, 2), "pico_MB": round(peak / 1e6, 1)}


def load_old_readers(commit: str) -> types.ModuleType:
    """Carrega o módulo de leitura da versão anterior a partir do git (para comparação)."""
    source = subprocess.run(  # noqa: S603 (comando fixo, sem entrada externa)
        ["git", "show", f"{commit}:apps/api/src/engiflow_api/infrastructure/readers.py"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    module = types.ModuleType("old_readers")
    sys.modules["old_readers"] = module  # dataclasses precisa do módulo registrado
    exec(compile(source, "old_readers.py", "exec"), module.__dict__)  # noqa: S102 (medição local)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=20_000)
    parser.add_argument("--old-commit", default="")
    args = parser.parse_args()
    limits = ImportLimits(max_rows=2_000_000)

    results: list[dict[str, float | str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        csv_path = base / "syn.csv"
        xlsx_path = base / "syn.xlsx"
        make_csv(csv_path, args.rows)
        make_xlsx(xlsx_path, args.rows)
        size_csv = csv_path.stat().st_size / 1e6
        print(f"amostra sintética: {args.rows} linhas; CSV {size_csv:.1f} MB")

        if args.old_commit:
            old = load_old_readers(args.old_commit)
            data = csv_path.read_bytes()
            results.append(
                measure(
                    "CSV leitura ANTIGA (bytes em memória)",
                    lambda: lambda: old.read_csv(data, limits),
                )
            )

        def new_csv_read() -> Callable[[], object]:
            def run() -> None:
                with open_csv(csv_path, limits) as stream:
                    for _ in stream.rows:
                        pass

            return run

        results.append(measure("CSV leitura NOVA (streaming)", new_csv_read))

        def full_import(source: Path) -> Callable[[], Callable[[], object]]:
            def make() -> Callable[[], object]:
                # Banco e pasta de armazenamento novos a cada rodada.
                round_dir = base / f"round-{uuid.uuid4().hex[:8]}"
                storage = round_dir / "originals"
                storage.mkdir(parents=True)
                engine = create_engine(f"sqlite:///{(round_dir / 'bench.db').as_posix()}")
                Base.metadata.create_all(engine)
                factory = sessionmaker(bind=engine, expire_on_commit=False)

                def run() -> None:
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    temp = storage / f".tmp-{uuid.uuid4().hex}"
                    temp.write_bytes(source.read_bytes())
                    with factory() as db:
                        ds.import_upload(
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
                    engine.dispose()

                return run

            return make

        results.append(measure("IMPORTAÇÃO completa CSV (grava no SQLite)", full_import(csv_path)))
        results.append(
            measure("IMPORTAÇÃO completa XLSX (grava no SQLite)", full_import(xlsx_path))
        )

    print()
    print(f"{'caso':<42}{'segundos':>10}{'pico_MB':>10}")
    for row in results:
        print(f"{row['caso']!s:<42}{row['segundos']!s:>10}{row['pico_MB']!s:>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
