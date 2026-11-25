import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EditableCell } from "@/components/data-studio/cell-editor";

function renderCells(handlers: {
  onPointer: (r: number, c: number, shift: boolean) => void;
  onExtend: (dr: number, dc: number) => void;
  onClear: () => void;
}, inRange = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <table>
        <tbody>
          <tr>
            <EditableCell
              datasetId="ds-1"
              rowNumber={7}
              rowIndex={0}
              colIndex={0}
              column="SYN-Código"
              value="x"
              range={{ inRange, ...handlers }}
            />
          </tr>
        </tbody>
      </table>
    </QueryClientProvider>,
  );
  return screen.getByRole("cell", { name: /SYN-Código, linha 7/ });
}

describe("seleção de intervalo pelo teclado na célula", () => {
  it("Shift+seta estende o intervalo sem mover o foco", () => {
    const handlers = { onPointer: vi.fn(), onExtend: vi.fn(), onClear: vi.fn() };
    const cell = renderCells(handlers);
    fireEvent.keyDown(cell, { key: "ArrowDown", shiftKey: true });
    expect(handlers.onExtend).toHaveBeenCalledWith(1, 0);
    expect(handlers.onPointer).not.toHaveBeenCalled();
  });

  it("seta sem Shift volta a seleção para esta célula", () => {
    const handlers = { onPointer: vi.fn(), onExtend: vi.fn(), onClear: vi.fn() };
    const cell = renderCells(handlers);
    fireEvent.keyDown(cell, { key: "ArrowRight" });
    expect(handlers.onPointer).toHaveBeenCalledWith(0, 0, false);
    expect(handlers.onExtend).not.toHaveBeenCalled();
  });

  it("Delete e Backspace pedem a limpeza do intervalo", () => {
    const handlers = { onPointer: vi.fn(), onExtend: vi.fn(), onClear: vi.fn() };
    const cell = renderCells(handlers, true);
    fireEvent.keyDown(cell, { key: "Delete" });
    fireEvent.keyDown(cell, { key: "Backspace" });
    expect(handlers.onClear).toHaveBeenCalledTimes(2);
    expect(cell.getAttribute("data-in-range")).toBe("1");
  });

  it("Shift+clique envia a informação de Shift ao intervalo", () => {
    const handlers = { onPointer: vi.fn(), onExtend: vi.fn(), onClear: vi.fn() };
    const cell = renderCells(handlers);
    fireEvent.mouseDown(cell, { shiftKey: true });
    expect(handlers.onPointer).toHaveBeenCalledWith(0, 0, true);
  });
});
