import { describe, expect, it } from "vitest";

import { exportDuplicatesPath, filenameFromDisposition } from "./datasets";

describe("exportação", () => {
  it("lê o nome do arquivo do Content-Disposition", () => {
    expect(filenameFromDisposition('attachment; filename="SYN_dados.csv"')).toBe("SYN_dados.csv");
    expect(filenameFromDisposition(null)).toBeNull();
    expect(filenameFromDisposition("attachment")).toBeNull();
  });

  it("monta o caminho de duplicatas com limite e descrições", () => {
    expect(exportDuplicatesPath("abc", 0.85)).toBe(
      "/api/v1/datasets/abc/duplicates/export?threshold=0.85&descriptions=true",
    );
  });
});
