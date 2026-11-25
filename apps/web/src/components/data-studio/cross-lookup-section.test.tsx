import { describe, expect, it } from "vitest";

import { buildLookupBody } from "@/components/data-studio/cross-lookup-section";

describe("buildLookupBody", () => {
  it("monta o contrato da API com chave única e colunas de retorno", () => {
    const body = buildLookupBody({
      leftId: "a",
      rightId: "b",
      leftKey: "Código",
      rightKey: "code",
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
});
