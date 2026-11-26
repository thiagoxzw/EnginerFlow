import { describe, expect, it } from "vitest";

import { cleanMapping, suggestMapping } from "@/components/bom/bom-import";

describe("sugestão de mapeamento do BOM", () => {
  it("separa código do pai de código do componente e ignora código alternativo", () => {
    const columns = ["Código alternativo", "Código pai", "Código", "Descrição", "Qtd", "Unidade", "Revisão"];
    const map = suggestMapping(columns);
    expect(map.parent_code).toBe("Código pai");
    expect(map.child_code).toBe("Código");
    expect(map.qty).toBe("Qtd");
    expect(map.unit).toBe("Unidade");
    expect(map.alt_code).toBe("Código alternativo");
  });

  it("nunca usa a mesma coluna para dois campos", () => {
    const map = suggestMapping(["Código", "Descrição"]);
    const values = Object.values(map);
    expect(new Set(values).size).toBe(values.length);
  });

  it("não sugere campo quando nenhum nome combina (decisão do usuário)", () => {
    expect(suggestMapping(["Coluna X", "Coluna Y"])).toEqual({});
  });

  it("remove campos sem coluna antes de enviar", () => {
    expect(cleanMapping({ child_code: "Código", qty: "", parent_code: "Código pai" })).toEqual({
      child_code: "Código",
      parent_code: "Código pai",
    });
  });
});
