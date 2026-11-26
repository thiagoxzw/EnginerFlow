import { afterEach, describe, expect, it, vi } from "vitest";

import { downloadBomExport } from "@/lib/bom";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("downloadBomExport", () => {
  it("mostra a mensagem de recusa da API em vez de erro genérico", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "A hierarquia de 'TOP' excede 200000 linhas." }), {
            status: 422,
            headers: { "content-type": "application/problem+json" },
          }),
      ),
    );
    await expect(
      downloadBomExport("rev-1", { kind: "hierarchy", fmt: "xlsx", root: "TOP" }),
    ).rejects.toThrow("A hierarquia de 'TOP' excede 200000 linhas.");
  });

  it("usa mensagem com o status quando a resposta de erro não tem detalhe", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>falha</html>", { status: 500 })));
    await expect(
      downloadBomExport("rev-1", { kind: "lines", fmt: "xlsx" }),
    ).rejects.toThrow("Exportação falhou (HTTP 500).");
  });
});
