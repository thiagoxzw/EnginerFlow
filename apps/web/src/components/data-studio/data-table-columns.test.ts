import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { readHiddenColumns, writeHiddenColumns } from "@/components/data-studio/data-table";

const KEY = "engiflow:colunas-ocultas:ds-test";

/** Armazenamento em memória com a mesma interface do localStorage (o jsdom da suíte não o expõe). */
function memoryStorage(failing = false): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    key: (i: number) => [...data.keys()][i] ?? null,
    getItem: (k: string) => {
      if (failing) throw new Error("bloqueado");
      return data.get(k) ?? null;
    },
    setItem: (k: string, v: string) => {
      if (failing) throw new Error("quota");
      data.set(k, String(v));
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
  };
}

function useStorage(storage: Storage) {
  Object.defineProperty(window, "localStorage", { value: storage, configurable: true });
}

describe("preferência de colunas ocultas", () => {
  beforeEach(() => useStorage(memoryStorage()));
  afterEach(() => useStorage(memoryStorage()));

  it("guarda e lê de volta as colunas ocultas desta tabela", () => {
    writeHiddenColumns(KEY, new Set(["Qtd", "Unidade"]));
    expect([...readHiddenColumns(KEY)].sort()).toEqual(["Qtd", "Unidade"]);
  });

  it("dados inválidos no armazenamento não quebram a tabela", () => {
    window.localStorage.setItem(KEY, "{não é json");
    expect(readHiddenColumns(KEY).size).toBe(0);
    window.localStorage.setItem(KEY, JSON.stringify({ a: 1 }));
    expect(readHiddenColumns(KEY).size).toBe(0);
  });

  it("armazenamento indisponível não lança erro (a preferência vale só na sessão)", () => {
    useStorage(memoryStorage(true));
    expect(() => writeHiddenColumns(KEY, new Set(["x"]))).not.toThrow();
    expect(readHiddenColumns(KEY).size).toBe(0);
  });
});
