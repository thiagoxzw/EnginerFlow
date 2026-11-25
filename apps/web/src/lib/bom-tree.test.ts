import { describe, expect, it } from "vitest";

import type { BomLine } from "@/lib/bom";
import {
  addDec,
  ancestorKeys,
  expandableKeys,
  formatDec,
  matchingLines,
  mulDec,
  parseDec,
  passesFilters,
  visibleRows,
} from "@/lib/bom-tree";

function L(line_no: number, parent: string | null, child: string | null, qty: string | null, extra: Partial<BomLine> = {}): BomLine {
  return {
    line_no,
    source_row: null,
    parent,
    child,
    description: null,
    qty,
    unit: "UN",
    rev: null,
    position: null,
    level: null,
    alt_code: null,
    manufacturer: null,
    part_number: null,
    notes: null,
    category: null,
    inferred_parent: false,
    ...extra,
  } as BomLine;
}

// Estrutura sintética: ônibus → tração (2) e bateria (1); ambos usam o motor.
const BUS: BomLine[] = [
  L(1, null, "ONIBUS-SYN", "1"),
  L(2, "ONIBUS-SYN", "CONJ-SYN-TRAC", "2", { description: "Tração" }),
  L(3, "ONIBUS-SYN", "CONJ-SYN-BAT", "1", { description: "Baterias" }),
  L(4, "CONJ-SYN-TRAC", "COMP-SYN-MOT", "4", { description: "Motor sintético" }),
  L(5, "CONJ-SYN-TRAC", "PARAF-SYN-M8", "0,5", { unit: "KG" }),
  L(6, "CONJ-SYN-BAT", "COMP-SYN-MOT", "1", { description: "Motor sintético" }),
];

describe("decimal exato", () => {
  it("multiplica sem erro de ponto flutuante", () => {
    expect(formatDec(mulDec(parseDec("0,5")!, parseDec("2")!))).toBe("1");
    expect(formatDec(mulDec(parseDec("0,1")!, parseDec("0,2")!))).toBe("0,02");
    expect(formatDec(addDec(parseDec("0,1")!, parseDec("0,2")!))).toBe("0,3");
  });

  it("aceita vírgula e ponto e rejeita texto", () => {
    expect(parseDec("1,5")?.n).toBe(15n);
    expect(parseDec("1.5")?.n).toBe(15n);
    expect(parseDec("abc")).toBeNull();
    expect(parseDec("")).toBeNull();
    expect(parseDec(null)).toBeNull();
  });

  it("formata sem zeros desnecessários e em pt-BR", () => {
    expect(formatDec(parseDec("10.00")!)).toBe("10");
    expect(formatDec(parseDec("2,50")!)).toBe("2,5");
    expect(formatDec(parseDec("0,05")!)).toBe("0,05");
  });
});

describe("árvore visível", () => {
  it("mostra só o topo quando nada está expandido", () => {
    const rows = visibleRows(BUS, new Set());
    expect(rows.map((r) => r.line.child)).toEqual(["ONIBUS-SYN"]);
    expect(rows[0]?.hasChildren).toBe(true);
  });

  it("expande um nível por vez e calcula a quantidade acumulada", () => {
    const rows = visibleRows(BUS, new Set(["1", "2", "3"]));
    const motors = rows.filter((r) => r.line.child === "COMP-SYN-MOT");
    expect(motors.map((r) => r.qtyAccumulated)).toEqual(["8", "1"]); // 2 × 4 e 1 × 1
    // Parafuso: 0,5 × 2 (tração) = 1 por veículo. Só aparece quando a tração está expandida.
    expect(rows.find((r) => r.line.child === "PARAF-SYN-M8")?.qtyAccumulated).toBe("1");
    const semTracao = visibleRows(BUS, new Set(["1"]));
    expect(semTracao.some((r) => r.line.child === "PARAF-SYN-M8")).toBe(false);
  });

  it("expandir tudo mostra todos os níveis", () => {
    const rows = visibleRows(BUS, expandableKeys(BUS));
    expect(rows.find((r) => r.line.child === "PARAF-SYN-M8")?.qtyAccumulated).toBe("1");
  });

  it("proteção contra ciclo: não desce novamente no mesmo caminho", () => {
    const cyc = [L(1, null, "A-SYN", "1"), L(2, "A-SYN", "B-SYN", "1"), L(3, "B-SYN", "A-SYN", "1")];
    const rows = visibleRows(cyc, new Set(["1", "2", "3"]));
    expect(rows.some((r) => r.cycle)).toBe(true);
  });
});

describe("busca, ancestrais e filtros", () => {
  it("encontra por código ou descrição, sem acento e sem caixa", () => {
    expect(matchingLines(BUS, "motor").size).toBe(2);
    expect(matchingLines(BUS, "PARAF").has("5")).toBe(true);
    expect(matchingLines(BUS, "   ").size).toBe(0);
  });

  it("expande o caminho até o resultado (ancestrais)", () => {
    const matched = matchingLines(BUS, "PARAF");
    const anc = ancestorKeys(BUS, matched);
    expect(anc.has("2")).toBe(true); // CONJ-SYN-TRAC é o pai do parafuso
    expect(anc.has("1")).toBe(true); // ONIBUS-SYN é o pai de CONJ-SYN-TRAC
  });

  it("filtra por nível, unidade e revisão", () => {
    const kg = BUS.filter((l) => passesFilters(l, { unit: "kg" }));
    expect(kg.map((l) => l.line_no)).toEqual([5]);
    expect(BUS.filter((l) => passesFilters(l, {})).length).toBe(BUS.length);
  });
});
