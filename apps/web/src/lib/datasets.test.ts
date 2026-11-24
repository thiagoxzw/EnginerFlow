import { describe, expect, it } from "vitest";

import { buildMappingPayload } from "./datasets";

describe("buildMappingPayload", () => {
  it("remove campos sem coluna escolhida", () => {
    expect(
      buildMappingPayload({ code: "Código", description: "", unit: undefined, quantity: "Qtd" }),
    ).toEqual({ code: "Código", quantity: "Qtd" });
  });

  it("retorna vazio quando nada foi mapeado", () => {
    expect(buildMappingPayload({})).toEqual({});
  });
});
