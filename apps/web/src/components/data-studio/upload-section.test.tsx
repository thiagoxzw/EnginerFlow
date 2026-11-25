import { describe, expect, it } from "vitest";

import {
  isAcceptedFile,
  planImports,
  type ImportItem,
} from "@/components/data-studio/upload-section";
import type { InspectOut } from "@/lib/datasets";

function info(kind: string, sheets: string[] = []): InspectOut {
  return {
    kind,
    sheets,
    sheet: sheets[0] ?? null,
    header_row: 1,
    columns: ["a"],
    preview: [],
    warnings: [],
  };
}

function item(name: string, partial: Partial<ImportItem>): ImportItem {
  return {
    key: name,
    file: new File(["x"], name),
    info: null,
    inspectError: null,
    sheets: [],
    done: [],
    status: "pendente",
    message: null,
    ...partial,
  };
}

describe("isAcceptedFile", () => {
  it("aceita apenas CSV e XLSX, sem diferenciar maiúsculas", () => {
    expect(isAcceptedFile("tabela.csv")).toBe(true);
    expect(isAcceptedFile("PLANILHA.XLSX")).toBe(true);
    expect(isAcceptedFile("foto.png")).toBe(false);
    expect(isAcceptedFile("dados.xls")).toBe(false);
  });
});

describe("planImports", () => {
  it("gera uma importação por aba marcada em XLSX e uma por CSV", () => {
    const plan = planImports([
      item("bom.xlsx", {
        info: info("xlsx", ["Rev A", "Rev B"]),
        sheets: ["Rev A", "Rev B"],
      }),
      item("kits.csv", { info: info("csv") }),
    ]);
    expect(plan.map((p) => [p.key, p.sheet])).toEqual([
      ["bom.xlsx", "Rev A"],
      ["bom.xlsx", "Rev B"],
      ["kits.csv", ""],
    ]);
  });

  it("ignora arquivos que não foram lidos ou tiveram erro de leitura", () => {
    const plan = planImports([
      item("ainda.csv", { info: null }),
      item("ruim.xlsx", { inspectError: "corrompido" }),
    ]);
    expect(plan).toEqual([]);
  });

  it("repetir a importação reenvia só o que não foi concluído (aba com erro, CSV pendente)", () => {
    const plan = planImports([
      item("bom.xlsx", {
        info: info("xlsx", ["Rev A", "Rev B"]),
        sheets: ["Rev A", "Rev B"],
        done: ["Rev A"],
        status: "erro",
      }),
      item("kits.csv", { info: info("csv"), done: [""], status: "importada" }),
      item("novo.csv", { info: info("csv"), done: [] }),
    ]);
    expect(plan.map((p) => [p.key, p.sheet])).toEqual([
      ["bom.xlsx", "Rev B"],
      ["novo.csv", ""],
    ]);
  });

  it("não importa XLSX sem nenhuma aba marcada", () => {
    const plan = planImports([item("vazio.xlsx", { info: info("xlsx", ["A"]), sheets: [] })]);
    expect(plan).toEqual([]);
  });
});
