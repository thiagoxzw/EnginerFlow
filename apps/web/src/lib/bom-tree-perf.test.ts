import { describe, expect, it } from "vitest";

import type { BomLine } from "@/lib/bom";
import { expandableKeys, matchingLines, passesFilters, visibleRows } from "@/lib/bom-tree";

/**
 * Medição sintética da árvore no navegador (mesma forma da medição da API).
 * Só roda com BOM_PERF=1. Pior caso: a árvore inteira expandida.
 */
const enabled = process.env.BOM_PERF === "1";

function synthetic(total: number): BomLine[] {
  const lines: BomLine[] = [];
  let n = 1;
  const add = (parent: string | null, child: string, qty: string, description: string) => {
    lines.push({
      line_no: n++,
      source_row: null,
      parent,
      child,
      description,
      qty,
      unit: "UN",
      rev: "A",
      position: null,
      level: null,
      alt_code: null,
      manufacturer: null,
      part_number: null,
      notes: null,
      category: null,
      inferred_parent: false,
    });
  };
  add(null, "TOP-SYN", "1", "Veículo sintético");
  const systems = 10;
  const subPerSystem = Math.max(2, Math.floor(total / 200));
  const leavesPerSub = Math.max(1, Math.floor((total - systems - systems * subPerSystem) / (systems * subPerSystem)));
  for (let s = 0; s < systems; s++) {
    const sys = `SYS-SYN-${String(s).padStart(2, "0")}`;
    add("TOP-SYN", sys, "1", `Sistema sintético ${s}`);
    for (let j = 0; j < subPerSystem; j++) {
      const sub = `SUB-SYN-${s}-${j}`;
      add(sys, sub, "2", "Subconjunto sintético");
      for (let k = 0; k < leavesPerSub; k++) {
        const leaf = `CMP-SYN-${(s * 37 + j * 11 + k) % Math.max(50, Math.floor(total / 4))}`;
        add(sub, leaf, String((k % 4) + 1), "Componente sintético");
      }
    }
  }
  return lines;
}

function time<T>(fn: () => T): { value: T; ms: number } {
  const started = performance.now();
  const value = fn();
  return { value, ms: Math.round((performance.now() - started) * 100) / 100 };
}

describe.skipIf(!enabled)("desempenho da árvore no navegador (sintético)", () => {
  for (const size of [1_000, 5_000, 10_000]) {
    it(`árvore com ${size} componentes`, () => {
      const lines = synthetic(size);
      const expandAll = expandableKeys(lines);
      const expanded = time(() => visibleRows(lines, expandAll));
      const searched = time(() => matchingLines(lines, "componente sintético"));
      const filtered = time(() => lines.filter((l) => passesFilters(l, { unit: "UN", rev: "A" })));
      const collapsed = time(() => visibleRows(lines, new Set()));
      console.log(
        JSON.stringify({
          componentes_alvo: size,
          linhas: lines.length,
          expandir_tudo_ms: expanded.ms,
          linhas_visiveis_expandido: expanded.value.length,
          busca_ms: searched.ms,
          busca_resultados: searched.value.size,
          filtro_ms: filtered.ms,
          recolhido_ms: collapsed.ms,
          recolhido_linhas: collapsed.value.length,
        }),
      );
      expect(collapsed.value.length).toBe(1);
    });
  }
});
