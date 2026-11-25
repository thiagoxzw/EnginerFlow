import { describe, expect, it } from "vitest";

import { buildCompareBody } from "@/components/data-studio/key-compare-section";

describe("buildCompareBody", () => {
  it("envia as chaves compostas na mesma ordem nos dois lados", () => {
    expect(
      buildCompareBody({
        leftId: "a",
        rightId: "b",
        keys: [
          { left: "Código", right: "code" },
          { left: "Unidade", right: "unit" },
        ],
      }),
    ).toEqual({
      left_id: "a",
      right_id: "b",
      left_keys: ["Código", "Unidade"],
      right_keys: ["code", "unit"],
    });
  });
});
