import { describe, expect, it } from "vitest";

import { buildJoinBody, needsGrowthConfirmation } from "@/components/data-studio/join-section";
import { derivedNotice } from "@/lib/datasets";

describe("derivedNotice", () => {
  it("informa nome, linhas, execução, hash e que as origens não mudaram", () => {
    const text = derivedNotice({
      name: "SYN-a × SYN-b",
      row_count: 3,
      run_id: "0123456789abcdef",
      result_sha256: "abcdef0123456789",
    });
    expect(text).toContain('"SYN-a × SYN-b" criada com 3 linhas');
    expect(text).toContain("Execução 01234567");
    expect(text).toContain("hash abcdef012345");
    expect(text).toContain("As tabelas de origem não foram alteradas.");
  });
});

describe("buildJoinBody", () => {
  it("envia chaves compostas na mesma ordem e o tipo de junção", () => {
    expect(
      buildJoinBody({
        leftId: "a",
        rightId: "b",
        keys: [
          { left: "Código", right: "code" },
          { left: "Unidade", right: "unit" },
        ],
        joinType: "left",
      }),
    ).toEqual({
      left_id: "a",
      right_id: "b",
      left_keys: ["Código", "Unidade"],
      right_keys: ["code", "unit"],
      join_type: "left",
    });
  });
});

describe("needsGrowthConfirmation", () => {
  it("exige confirmação só para N:M", () => {
    expect(needsGrowthConfirmation("N:M")).toBe(true);
    expect(needsGrowthConfirmation("1:1")).toBe(false);
    expect(needsGrowthConfirmation("1:N")).toBe(false);
    expect(needsGrowthConfirmation("N:1")).toBe(false);
  });
});
