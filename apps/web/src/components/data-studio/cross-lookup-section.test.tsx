import { describe, expect, it } from "vitest";

import { keysComplete } from "@/components/data-studio/key-pairs";
import { buildLookupBody, formatKeys } from "@/components/data-studio/cross-lookup-section";

describe("formatKeys", () => {
  it("mostra chaves compostas com separador legível e preserva zeros", () => {
    expect(formatKeys(["000210|CH", "000500|PC"])).toBe("000210 + CH · 000500 + PC");
  });

  it("limita a amostra", () => {
    expect(formatKeys(["a", "b", "c"], 2)).toBe("a · b");
  });
});

describe("buildLookupBody", () => {
  it("monta o contrato da API com chave simples e colunas de retorno", () => {
    const body = buildLookupBody({
      leftId: "a",
      rightId: "b",
      keys: [{ left: "Código", right: "code" }],
      returns: ["Unidade"],
      duplicates: "first",
      unmatched: "keep_empty",
    });
    expect(body).toEqual({
      left_id: "a",
      right_id: "b",
      left_keys: ["Código"],
      right_keys: ["code"],
      return_columns: ["Unidade"],
      duplicates: "first",
      unmatched: "keep_empty",
    });
  });

  it("envia chaves compostas na mesma ordem nos dois lados", () => {
    const body = buildLookupBody({
      leftId: "a",
      rightId: "b",
      keys: [
        { left: "Código", right: "code" },
        { left: "Unidade", right: "unit" },
      ],
      returns: [],
      duplicates: "all",
      unmatched: "drop",
    });
    expect(body.left_keys).toEqual(["Código", "Unidade"]);
    expect(body.right_keys).toEqual(["code", "unit"]);
  });
});

describe("keysComplete", () => {
  it("exige que todos os pares tenham os dois lados preenchidos", () => {
    expect(keysComplete([{ left: "a", right: "" }])).toBe(false);
    expect(keysComplete([{ left: "a", right: "b" }, { left: "", right: "c" }])).toBe(false);
    expect(keysComplete([{ left: "a", right: "b" }])).toBe(true);
  });

  it("não aceita lista vazia", () => {
    expect(keysComplete([])).toBe(false);
  });
});
