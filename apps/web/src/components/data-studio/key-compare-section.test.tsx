import { describe, expect, it } from "vitest";

import {
  buildCompareBody,
  sharedCompareColumns,
} from "@/components/data-studio/key-compare-section";

describe("sharedCompareColumns", () => {
  it("lista colunas de mesmo nome que não são chave, sem diferenciar caixa", () => {
    expect(
      sharedCompareColumns(
        ["Código", "Unidade", "Preço", "Local"],
        ["codigo", "UNIDADE", "preço", "Outra"],
        ["Código"],
        ["codigo"],
      ),
    ).toEqual(["Unidade", "Preço"]);
  });

  it("não inclui a coluna de chave da tabela de busca mesmo com nome igual a outra coluna", () => {
    expect(sharedCompareColumns(["A", "B"], ["B", "A"], ["A"], ["B"])).toEqual([]);
  });
});

describe("buildCompareBody", () => {
  it("envia chaves compostas na ordem e o modo de TODAS as colunas comparadas", () => {
    expect(
      buildCompareBody({
        leftId: "a",
        rightId: "b",
        keys: [
          { left: "Código", right: "code" },
          { left: "Unidade", right: "unit" },
        ],
        shared: ["Preço", "Descrição"],
        modes: { Preço: "numerico" },
      }),
    ).toEqual({
      left_id: "a",
      right_id: "b",
      left_keys: ["Código", "Unidade"],
      right_keys: ["code", "unit"],
      modes: { Preço: "numerico", Descrição: "exato" },
    });
  });

  it("o padrão é texto exato: colunas sem escolha não ganham equivalência numérica", () => {
    const body = buildCompareBody({
      leftId: "a",
      rightId: "b",
      keys: [{ left: "Código", right: "code" }],
      shared: ["Qtd"],
      modes: {},
    });
    expect(body.modes).toEqual({ Qtd: "exato" });
  });
});
