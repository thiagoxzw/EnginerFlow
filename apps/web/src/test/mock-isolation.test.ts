import { describe, expect, it, vi } from "vitest";

// Regressão: valores enfileirados com mockResolvedValueOnce não podem vazar para o teste seguinte.
// Antes, vi.clearAllMocks() deixava a fila. O setup global agora usa resetAllMocks após cada teste.
const service = { load: vi.fn<() => Promise<string>>() };

describe("isolamento de mocks entre testes", () => {
  it("A: enfileira um valor e não o consome", () => {
    service.load.mockResolvedValueOnce("VALOR-DO-TESTE-A");
    expect(service.load).toBeDefined();
  });

  it("B: sem configuração própria, o mock não devolve o valor de A", async () => {
    const result = await service.load();
    expect(result).toBeUndefined();
  });
});
