import { describe, expect, it } from "vitest";

import {
  bulkValueCells,
  clearRangeCells,
  extendRange,
  fillDownCells,
  normalizeRange,
  pageRange,
  rangeContains,
  rangeValues,
  type CellRange,
} from "@/lib/range";

const rows = [{ row_number: 10 }, { row_number: 11 }, { row_number: 12 }];
const columns = ["A", "B", "C"];

describe("intervalo de células", () => {
  it("normaliza independentemente da direção da seleção", () => {
    const range: CellRange = { anchor: { rowIndex: 2, colIndex: 2 }, focus: { rowIndex: 0, colIndex: 1 } };
    expect(normalizeRange(range)).toEqual({ r0: 0, r1: 2, c0: 1, c1: 2 });
    expect(rangeContains(range, 1, 1)).toBe(true);
    expect(rangeContains(range, 1, 0)).toBe(false);
    expect(rangeContains(null, 0, 0)).toBe(false);
  });

  it("Shift+seta move só a ponta e fica dentro da página", () => {
    const start: CellRange = { anchor: { rowIndex: 0, colIndex: 0 }, focus: { rowIndex: 0, colIndex: 0 } };
    const moved = extendRange(start, 1, 1, 2, 2);
    expect(moved.anchor).toEqual({ rowIndex: 0, colIndex: 0 });
    expect(moved.focus).toEqual({ rowIndex: 1, colIndex: 1 });
    const limit = extendRange(moved, 5, 5, 2, 2);
    expect(limit.focus).toEqual({ rowIndex: 2, colIndex: 2 });
    expect(extendRange(start, -1, -1, 2, 2).focus).toEqual({ rowIndex: 0, colIndex: 0 });
  });

  it("limpa somente células visíveis do intervalo, em uma lista de atribuições", () => {
    const range: CellRange = { anchor: { rowIndex: 0, colIndex: 0 }, focus: { rowIndex: 1, colIndex: 1 } };
    const cells = clearRangeCells(range, rows, columns, new Set());
    expect(cells).toEqual([
      { row_number: 10, column: "A", value: "" },
      { row_number: 10, column: "B", value: "" },
      { row_number: 11, column: "A", value: "" },
      { row_number: 11, column: "B", value: "" },
    ]);
  });

  it("não limpa colunas ocultas, mesmo dentro do intervalo", () => {
    const range: CellRange = { anchor: { rowIndex: 0, colIndex: 0 }, focus: { rowIndex: 0, colIndex: 2 } };
    const cells = clearRangeCells(range, rows, columns, new Set(["B"]));
    expect(cells.map((c) => c.column)).toEqual(["A", "C"]);
  });

  it("copia o intervalo preservando vazio, desconhecido e zeros à esquerda", () => {
    const grid = [
      { row_number: 10, values: ["007", "", null] as (string | null)[] },
      { row_number: 11, values: ["0", "x", "y"] as (string | null)[] },
    ];
    const range: CellRange = { anchor: { rowIndex: 0, colIndex: 0 }, focus: { rowIndex: 1, colIndex: 2 } };
    expect(rangeValues(range, grid, new Set(["B"]), columns)).toEqual([
      ["007", null],
      ["0", "y"],
    ]);
  });

  it("preenchimento para baixo copia a primeira linha e propaga desconhecido como desconhecido", () => {
    const grid = [
      { row_number: 10, values: ["ABC", null] as (string | null)[] },
      { row_number: 11, values: ["", "q"] as (string | null)[] },
      { row_number: 12, values: ["", "r"] as (string | null)[] },
    ];
    const range: CellRange = { anchor: { rowIndex: 0, colIndex: 0 }, focus: { rowIndex: 2, colIndex: 1 } };
    const cells = fillDownCells(range, grid, ["A", "B"], new Set());
    expect(cells).toHaveLength(4);
    expect(cells.find((c) => c.row_number === 12 && c.column === "A")?.value).toBe("ABC");
    expect(cells.find((c) => c.row_number === 11 && c.column === "B")?.value).toBeNull();
  });

  it("edição em massa grava o mesmo valor em cada célula visível do intervalo", () => {
    const range: CellRange = { anchor: { rowIndex: 0, colIndex: 0 }, focus: { rowIndex: 1, colIndex: 1 } };
    const cells = bulkValueCells(range, rows, columns, new Set(), "007");
    expect(cells).toHaveLength(4);
    expect(cells.every((c) => c.value === "007")).toBe(true);
  });

  it("Ctrl+A seleciona a página inteira e nada numa página vazia", () => {
    expect(pageRange(3, 3)).toEqual({
      anchor: { rowIndex: 0, colIndex: 0 },
      focus: { rowIndex: 2, colIndex: 2 },
    });
    expect(pageRange(0, 3)).toBeNull();
  });
});
