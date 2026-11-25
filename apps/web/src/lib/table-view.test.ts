import { beforeEach, describe, expect, it } from "vitest";

import {
  clampWidth,
  displayOrder,
  emptyView,
  fitWidth,
  MAX_WIDTH,
  MIN_WIDTH,
  moveColumn,
  readTableView,
  reconcileView,
  setWidth,
  togglePin,
  viewKey,
  writeTableView,
} from "@/lib/table-view";

const COLS = ["A", "B", "C", "D"];

// Armazenamento em memória: jsdom não expõe localStorage neste projeto (ver test/setup.ts).
beforeEach(() => {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    },
  });
});

describe("visão da tabela", () => {
  it("reconcilia: descarta colunas que sumiram e acrescenta as novas no fim", () => {
    const view = reconcileView({ order: ["C", "X", "A"], widths: { X: 90, A: 200 }, pinned: ["A", "X"] }, COLS);
    expect(view.order).toEqual(["C", "A", "B", "D"]);
    expect(view.widths).toEqual({ A: 200 });
    expect(view.pinned).toEqual(["A"]);
  });

  it("exibe as fixadas primeiro, na ordem delas", () => {
    let view = emptyView(COLS);
    view = togglePin(view, "C");
    view = togglePin(view, "A");
    expect(displayOrder(view)).toEqual(["A", "C", "B", "D"]);
  });

  it("move colunas e ignora movimentos inválidos nas bordas", () => {
    const view = emptyView(COLS);
    expect(moveColumn(view, "B", -1).order).toEqual(["B", "A", "C", "D"]);
    expect(moveColumn(view, "A", -1)).toBe(view);
    expect(moveColumn(view, "D", 1)).toBe(view);
    expect(moveColumn(view, "Z", 1)).toBe(view);
  });

  it("limita a largura aos extremos", () => {
    expect(clampWidth(1)).toBe(MIN_WIDTH);
    expect(clampWidth(10_000)).toBe(MAX_WIDTH);
    expect(setWidth(emptyView(COLS), "A", 5000).widths.A).toBe(MAX_WIDTH);
  });

  it("ajuste automático segue o conteúdo mais longo, dentro dos limites", () => {
    expect(fitWidth("Q", ["x", null])).toBe(MIN_WIDTH);
    expect(fitWidth("Q", ["a".repeat(200)])).toBe(MAX_WIDTH);
    expect(fitWidth("Código", ["00123"])).toBeGreaterThan(MIN_WIDTH);
  });

  it("persiste por tabela e lê de volta; conteúdo inválido vira visão padrão", () => {
    const key = viewKey("ds-1");
    writeTableView(key, { order: ["D", "A"], widths: { A: 120 }, pinned: ["D"] });
    const back = readTableView(key, COLS);
    expect(back.pinned).toEqual(["D"]);
    expect(back.widths).toEqual({ A: 120 });
    expect(back.order.slice(0, 2)).toEqual(["D", "A"]);

    window.localStorage.setItem(key, "{not json");
    expect(readTableView(key, COLS)).toEqual(emptyView(COLS));
    window.localStorage.setItem(key, JSON.stringify({ widths: { A: "x" } }));
    expect(readTableView(key, COLS).widths).toEqual({});
  });

  it("chaves de tabelas diferentes não se misturam", () => {
    expect(viewKey("ds-1")).not.toBe(viewKey("ds-2"));
  });
});
