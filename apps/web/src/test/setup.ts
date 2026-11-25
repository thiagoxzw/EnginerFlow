import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Isolamento entre testes.
// - cleanup: desmonta a árvore React de cada teste.
// - resetAllMocks: zera implementações E filas de mockResolvedValueOnce/mockReturnValueOnce.
//   vi.clearAllMocks() NÃO faz isso: um valor enfileirado e não consumido vazava para o teste seguinte
//   (comprovado em src/test/mock-isolation.test.ts).
// - restoreAllMocks: devolve espiões (vi.spyOn) ao original.
// - unstubAllGlobals: remove stubs de globais (fetch, etc.).
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
