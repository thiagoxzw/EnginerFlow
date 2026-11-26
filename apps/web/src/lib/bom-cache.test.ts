import { describe, expect, it } from "vitest";

import { keepPreviousLines } from "@/lib/bom-cache";

const linhasDaEstruturaA = { lines: [{ child: "COMP-A" }] };

describe("keepPreviousLines", () => {
  it("mantém as linhas enquanto a revisão nova da mesma estrutura carrega", () => {
    const key = ["bom-lines", "estrutura-a", "rev-1"];
    expect(keepPreviousLines(linhasDaEstruturaA, key, "estrutura-a")).toBe(linhasDaEstruturaA);
  });

  it("não reaproveita linhas de outra estrutura ao trocar de estrutura", () => {
    const key = ["bom-lines", "estrutura-a", "rev-1"];
    expect(keepPreviousLines(linhasDaEstruturaA, key, "estrutura-b")).toBeUndefined();
  });

  it("sem consulta anterior não há o que reaproveitar", () => {
    expect(keepPreviousLines(undefined, undefined, "estrutura-a")).toBeUndefined();
  });

  it("sem estrutura selecionada não reaproveita dados de uma estrutura", () => {
    const key = ["bom-lines", "estrutura-a", "rev-1"];
    expect(keepPreviousLines(linhasDaEstruturaA, key, null)).toBeUndefined();
  });
});
