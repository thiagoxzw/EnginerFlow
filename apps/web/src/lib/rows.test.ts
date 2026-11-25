import { describe, expect, it } from "vitest";

import { buildRowsParams, isComplete } from "@/lib/rows";

const BASE = { offset: 0, limit: 50, q: "", sort: null, dir: "asc" as const };

describe("buildRowsParams", () => {
  it("envia apenas filtros completos e preserva valores exatamente como digitados", () => {
    const params = buildRowsParams({
      ...BASE,
      filters: [
        { column: "SYN-Código", op: "eq", value: "00123" },
        { column: "Qtd", op: "gt", value: "" }, // incompleto: não enviado
        { column: "Qtd", op: "between", value: "1,5", value2: "9" },
        { column: "Qtd", op: "is_zero" },
      ],
    });
    const sent = JSON.parse(params.get("filters") ?? "[]");
    expect(sent).toEqual([
      { column: "SYN-Código", op: "eq", value: "00123" },
      { column: "Qtd", op: "between", value: "1,5", value2: "9" },
      { column: "Qtd", op: "is_zero" },
    ]);
  });

  it("não envia parâmetros vazios e inclui ordenação só quando escolhida", () => {
    const plain = buildRowsParams({ ...BASE, filters: [] });
    expect(plain.has("filters")).toBe(false);
    expect(plain.has("q")).toBe(false);
    expect(plain.has("sort")).toBe(false);

    const sorted = buildRowsParams({ ...BASE, q: "  parafuso ", filters: [], sort: "Qtd", dir: "desc" });
    expect(sorted.get("q")).toBe("parafuso");
    expect(sorted.get("sort")).toBe("Qtd");
    expect(sorted.get("dir")).toBe("desc");
  });
});

describe("isComplete", () => {
  it("exige dois valores em 'entre' e valor em operadores de comparação", () => {
    expect(isComplete({ column: "a", op: "between", value: "1" })).toBe(false);
    expect(isComplete({ column: "a", op: "between", value: "1", value2: "2" })).toBe(true);
    expect(isComplete({ column: "a", op: "lt", value: " " })).toBe(false);
    expect(isComplete({ column: "a", op: "is_unknown" })).toBe(true);
  });
});
