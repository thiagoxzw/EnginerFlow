"""Fase 4: medição sintética de desempenho do BOM (1.000, 5.000 e 10.000 componentes).

Só roda com BOM_PERF=1 (não entra na suíte normal). Resultado em JSON no caminho de BOM_PERF_OUT.
Dados totalmente sintéticos (BOM-SYN-*). Mede: importação, criação da estrutura, leitura das
linhas, validação, explosão, comparação e pico de memória das funções de cálculo.
"""

from __future__ import annotations

import json
import os
import time
import tracemalloc
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from engiflow_api.core.config import Settings
from engiflow_api.domain.bom import BomLine, compare, explode, validate

SIZES = (1_000, 5_000, 10_000)
enabled = os.environ.get("BOM_PERF") == "1"
pytestmark = pytest.mark.skipif(not enabled, reason="Medição de desempenho: defina BOM_PERF=1.")


def _csv(total: int) -> tuple[bytes, int]:
    rows = ["Código pai;Código;Descrição;Qtd;Unidade;Revisão"]
    rows.append(";TOP-SYN;Veículo sintético;1;UN;A")
    subsystems = 10
    sub_per_system = max(2, total // 200)
    leaves_per_sub = max(
        1, (total - subsystems - subsystems * sub_per_system) // (subsystems * sub_per_system)
    )
    count = 1
    for s in range(subsystems):
        sys_code = f"SYS-SYN-{s:02d}"
        rows.append(f"TOP-SYN;{sys_code};Sistema sintético {s};1;UN;A")
        for j in range(sub_per_system):
            sub_code = f"SUB-SYN-{s:02d}-{j:04d}"
            rows.append(f"{sys_code};{sub_code};Subconjunto sintético;2;UN;A")
            for k in range(leaves_per_sub):
                # Componentes reaproveitados entre subconjuntos (mesmo código em vários pais).
                leaf = f"CMP-SYN-{(s * 37 + j * 11 + k) % max(50, total // 4):05d}"
                rows.append(f"{sub_code};{leaf};Componente sintético;{(k % 4) + 1};UN;A")
                count += 1
    return ("\n".join(rows) + "\n").encode("utf-8"), len(rows) - 1


def _lines_from(raw: list[dict[str, Any]]) -> list[BomLine]:
    return [
        BomLine(
            line_no=r["line_no"],
            parent=r["parent"],
            child=r["child"],
            description=r["description"],
            qty_raw=r["qty"],
            unit=r["unit"],
            rev=r["rev"],
            position=r["position"],
            level=r["level"],
            alt_code=r["alt_code"],
            manufacturer=r["manufacturer"],
            part_number=r["part_number"],
            notes=r["notes"],
            source_row=r["source_row"],
            inferred_parent=r["inferred_parent"],
        )
        for r in raw
    ]


def _peak_mb(fn: Any) -> tuple[float, float]:
    tracemalloc.start()
    started = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, peak / (1024 * 1024)


@pytest.mark.parametrize("size", SIZES)
def test_desempenho_bom_sintetico(
    logged_client: TestClient, storage_settings: Settings, size: int
) -> None:
    results: dict[str, Any] = {"componentes_alvo": size}
    raw, lines_count = _csv(size)
    results["linhas_reais"] = lines_count
    name = f"SYN-perf-{size}-{uuid.uuid4().hex[:6]}"

    t = time.perf_counter()
    resp = logged_client.post("/api/v1/datasets", files={"file": (f"{name}.csv", raw, "text/csv")})
    results["importacao_tabela_s"] = round(time.perf_counter() - t, 3)
    assert resp.status_code == 201, resp.text
    dataset = resp.json()["dataset"]

    mapping = {
        "parent_code": "Código pai",
        "child_code": "Código",
        "description": "Descrição",
        "qty": "Qtd",
        "unit": "Unidade",
        "rev": "Revisão",
    }
    t = time.perf_counter()
    prev = logged_client.post(
        "/api/v1/bom/preview",
        json={"dataset_id": dataset["id"], "mapping": mapping, "mode": "explicit"},
    )
    results["previa_s"] = round(time.perf_counter() - t, 3)
    assert prev.status_code == 200, prev.text

    t = time.perf_counter()
    created = logged_client.post(
        "/api/v1/bom/structures",
        json={
            "name": f"BOM {name}",
            "dataset_id": dataset["id"],
            "mapping": mapping,
            "mode": "explicit",
        },
    )
    results["criacao_estrutura_s"] = round(time.perf_counter() - t, 3)
    assert created.status_code == 201, created.text
    rid = created.json()["revision_id"]

    t = time.perf_counter()
    raw_lines = logged_client.get(f"/api/v1/bom/revisions/{rid}/lines").json()["lines"]
    results["leitura_linhas_s"] = round(time.perf_counter() - t, 3)
    lines = _lines_from(raw_lines)
    results["linhas_gravadas"] = len(lines)

    t = time.perf_counter()
    explosion = logged_client.post(
        f"/api/v1/bom/revisions/{rid}/explode", json={"root": "TOP-SYN", "vehicles": "100"}
    )
    results["explosao_api_s"] = round(time.perf_counter() - t, 3)
    assert explosion.status_code == 200, explosion.text
    results["codigos_consolidados"] = len(explosion.json()["consolidated"])

    elapsed, peak = _peak_mb(lambda: explode(lines, "TOP-SYN", __import__("decimal").Decimal(100)))
    results["explosao_dominio_s"] = round(elapsed, 3)
    results["explosao_pico_memoria_mb"] = round(peak, 2)

    elapsed, peak = _peak_mb(lambda: validate(lines, "explicit"))
    results["validacao_dominio_s"] = round(elapsed, 3)
    results["validacao_pico_memoria_mb"] = round(peak, 2)

    changed = [*lines]
    changed[len(changed) // 2] = BomLine(**{**changed[len(changed) // 2].__dict__, "qty_raw": "9"})
    elapsed, peak = _peak_mb(lambda: compare(lines, changed))
    results["comparacao_dominio_s"] = round(elapsed, 3)
    results["comparacao_pico_memoria_mb"] = round(peak, 2)

    t = time.perf_counter()
    needle = "componente sintético"
    hits = sum(1 for line in lines if line.description and needle in line.description.lower())
    results["busca_texto_s"] = round(time.perf_counter() - t, 4)
    results["busca_resultados"] = hits

    out = os.environ.get("BOM_PERF_OUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(results, ensure_ascii=False) + "\n")
    assert results["linhas_gravadas"] == lines_count
