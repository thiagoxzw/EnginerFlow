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
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from engiflow_api.application import crossing as cx
from engiflow_api.application import data_studio as ds
from engiflow_api.domain import lookup as lk
from engiflow_api.domain.errors import DomainError
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


def make_unique_left(path: Path, rows: int) -> None:
    """Cenário dentro do limite: chaves únicas 1..N (sem duplicatas)."""
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("SYN-Código;SYN-Unidade;SYN-Qtd\n")
        for i in range(1, rows + 1):
            fh.write(f"{i:08d};UN;{i % 9},5\n")


def make_unique_right(path: Path, rows: int) -> None:
    """Cenário dentro do limite: chaves únicas, 60% de sobreposição com a consulta.

    Consulta 1..N e busca [0,4N/10 + 1 .. 0,4N/10 + N]: casam 0,6N, removem 0,4N e adicionam 0,4N.
    Com N=500 mil: 300 mil casadas, 200 mil removidas e 200 mil adicionadas (400 mil diferenças < 500 mil).
    """
    start = rows * 2 // 5 + 1
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("SYN-Código;SYN-Unidade;SYN-Preço\n")
        for i in range(start, start + rows):
            fh.write(f"{i:08d};UN;{i % 1000},25\n")


def process_peak_mb() -> float:
    """Pico de working set do PRÓPRIO processo Python (Windows, via GetProcessMemoryInfo)."""
    if platform.system() != "Windows":
        return 0.0
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = ctypes.WinDLL("kernel32").GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    if not ok:
        raise RuntimeError("GetProcessMemoryInfo falhou; o pico do processo não pode ser medido.")
    return round(counters.PeakWorkingSetSize / 1e6, 1)


def measure(label: str, action: Callable[[], Any]) -> dict[str, Any]:
    """Tempo, pico Python (tracemalloc), pico do processo e linhas de saída de UMA operação."""
    started = time.perf_counter()
    output = action()
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
        "pico_processo_MB": process_peak_mb(),
        "saida": output,
    }


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
    parser.add_argument(
        "--scenario",
        choices=["duplicates", "within-limit"],
        default="duplicates",
        help="duplicates: chaves repetidas (junção/comparação acima do limite, recusadas); "
        "within-limit: chaves únicas (resultado dentro do limite).",
    )
    parser.add_argument("--results-file", default="", help="arquivo onde cada resultado é anexado")
    args = parser.parse_args()
    results_file = args.results_file
    url = os.environ.get("ENGIFLOW_BENCH_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        print("Defina ENGIFLOW_BENCH_DATABASE_URL com um PostgreSQL de teste.", file=sys.stderr)
        return 2
    # Proteção: este script apaga o schema public. Só roda em banco dedicado ao benchmark,
    # em host local, e nunca na porta do ambiente demonstrativo (5432).
    parsed = make_url(url)
    if parsed.database != "engiflow_bench" or parsed.host not in ("127.0.0.1", "localhost"):
        print("Recusado: o benchmark exige o banco 'engiflow_bench' em 127.0.0.1.", file=sys.stderr)
        return 2
    if parsed.port in (None, 5432):
        print("Recusado: porta 5432 é do ambiente demonstrativo. Use o PostgreSQL de benchmark.", file=sys.stderr)
        return 2

    engine = create_engine(url)
    reset_schema(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    limits = ImportLimits(max_rows=2_000_000)
    results: list[dict[str, Any]] = []
    print(f"amostra sintética: {args.rows} linhas de entrada por tabela; cenário: {args.scenario}")
    for line in environment(engine):
        print(line)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        storage = base / "originals"
        storage.mkdir()
        files = {"left": base / "consulta.csv", "right": base / "busca.csv"}
        if args.scenario == "within-limit":
            make_unique_left(files["left"], args.rows)
            make_unique_right(files["right"], args.rows)
        else:
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
        import_line = (
            "RESULTADO | importação das duas tabelas | "
            f"segundos={round(time.perf_counter() - started, 3)} | "
            f"pico_processo_MB={process_peak_mb()} | linhas_entrada={args.rows} por tabela"
        )
        print(import_line, flush=True)
        if results_file:
            with Path(results_file).open("a", encoding="utf-8") as out:
                out.write(import_line + "\n")
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

        def lookup_preview(db: DbSession, left: Dataset, right: Dataset) -> int:
            spec = cx.LookupSpec(
                left_keys=keys_left,
                right_keys=keys_right,
                return_columns=("SYN-Preço",),
                policy=lk.LookupPolicy(duplicates="first", unmatched="keep_empty"),
            )
            outcome = cx.run_lookup(db, left, right, spec, max_output_rows=2_000_000)
            return len(outcome.result.rows)

        refusals: dict[str, str] = {}

        def join_preview(db: DbSession, left: Dataset, right: Dataset) -> int | str:
            # A recusa por cardinalidade acontece no planejamento, antes de materializar linhas.
            try:
                outcome = cx.run_join(db, left, right, keys_left, keys_right, "left")
                return outcome.plan.estimated_rows
            except DomainError as exc:
                refusals["junção esquerda"] = str(exc)
                return "recusada"

        def compare_preview(db: DbSession, left: Dataset, right: Dataset) -> int | str:
            # A comparação recusa ao atingir o limite DURANTE o streaming (linhas já emitidas).
            try:
                result = cx.run_comparison(
                    db, left, right, cx.ComparisonSpec(left_keys=keys_left, right_keys=keys_right)
                )
                return len(result.rows)
            except DomainError as exc:
                refusals["comparação por chave"] = str(exc)
                return "recusada"

        def aggregate_preview(db: DbSession, left: Dataset, _right: Dataset) -> int:
            result = cx.run_aggregate(
                db,
                left,
                cx.AggregateSpec(group_by=("SYN-Unidade",), measures=(("SYN-Qtd", "sum"),)),
            )
            return len(result.rows)

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
            row = results[-1]
            line = (
                f"RESULTADO | {row['caso']} | segundos={row['segundos']} | "
                f"pico_python_MB={row['pico_MB']} | pico_processo_MB={row['pico_processo_MB']} | "
                f"saida={row['saida']}"
            )
            # Registro imediato: no stdout e num arquivo próprio, gravado e fechado a cada resultado.
            print(line, flush=True)
            if results_file:
                with Path(results_file).open("a", encoding="utf-8") as out:
                    out.write(line + "\n")

        derive_started = time.perf_counter()
        with_pair(lookup_derive)()
        derive_row = {
            "caso": "Super-PROCV: criação de tabela derivada (uma vez)",
            "segundos": round(time.perf_counter() - derive_started, 3),
            "pico_MB": "n/a",
            "pico_processo_MB": process_peak_mb(),
            "saida": "gravada",
        }
        results.append(derive_row)
        derive_line = f"RESULTADO | {derive_row['caso']} | segundos={derive_row['segundos']}"
        print(derive_line, flush=True)
        if results_file:
            with Path(results_file).open("a", encoding="utf-8") as out:
                out.write(derive_line + "\n")

    print()
    print(f"{'caso':<56}{'segundos':>10}{'pico_py_MB':>12}{'pico_proc_MB':>14}{'saída':>12}")
    for row in results:
        print(
            f"{row['caso']!s:<56}{row['segundos']!s:>10}{row['pico_MB']!s:>12}"
            f"{row.get('pico_processo_MB', 'n/a')!s:>14}{row.get('saida', 'n/a')!s:>12}"
        )
    for case, message in refusals.items():
        print(f"recusa esperada ({case}): {message}")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
