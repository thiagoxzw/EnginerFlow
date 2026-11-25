import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EditableCell } from "@/components/data-studio/cell-editor";
import * as ops from "@/lib/operations";
import * as tpl from "@/lib/templates";

vi.mock("@/lib/operations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/operations")>("@/lib/operations");
  return { ...actual, previewOperation: vi.fn(), applyOperation: vi.fn() };
});
vi.mock("@/lib/templates", async () => {
  const actual = await vi.importActual<typeof import("@/lib/templates")>("@/lib/templates");
  return { ...actual, getDatasetState: vi.fn() };
});
vi.mock("@/lib/invalidate", () => ({ invalidateDataset: vi.fn(async () => undefined) }));

const STATE = { dataVersionId: "v-1", metadataVersionId: "m-1" };

function renderCell(value: string | null) {
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
              value={value}
              range={{ inRange: false, onPointer: () => {}, onExtend: () => {}, onClear: () => {} }}
            />
          </tr>
        </tbody>
      </table>
    </QueryClientProvider>,
  );
}

describe("EditableCell", () => {
  beforeEach(() => {
    vi.mocked(tpl.getDatasetState).mockResolvedValue(STATE);
    vi.mocked(ops.previewOperation).mockResolvedValue({ preview_id: "p-1" } as ops.OperationPreview);
    vi.mocked(ops.applyOperation).mockResolvedValue(undefined);
  });

  it("duplo clique, digitação e Enter gravam só a célula, pela prévia e aplicação", async () => {
    const user = userEvent.setup();
    renderCell("00123");
    await user.dblClick(screen.getByRole("cell", { name: /SYN-Código, linha 7/ }));
    const input = screen.getByRole("textbox", { name: "Editar SYN-Código da linha 7" });
    await user.clear(input);
    await user.type(input, "000999{Enter}");

    await waitFor(() => expect(ops.applyOperation).toHaveBeenCalledTimes(1));
    expect(ops.previewOperation).toHaveBeenCalledWith(
      "ds-1",
      "set_rows_value",
      { row_numbers: [7], column: "SYN-Código", value: "000999" },
      STATE,
    );
    expect(ops.applyOperation).toHaveBeenCalledWith("ds-1", "p-1", STATE);
  });

  it("Escape cancela a edição sem gravar", async () => {
    const user = userEvent.setup();
    renderCell("00123");
    await user.dblClick(screen.getByRole("cell", { name: /SYN-Código, linha 7/ }));
    const input = screen.getByRole("textbox", { name: "Editar SYN-Código da linha 7" });
    await user.type(input, "X{Escape}");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(ops.previewOperation).not.toHaveBeenCalled();
    expect(ops.applyOperation).not.toHaveBeenCalled();
  });

  it("Enter sem alteração não grava nada (nenhuma linha é alterada à toa)", async () => {
    const user = userEvent.setup();
    renderCell("00123");
    await user.dblClick(screen.getByRole("cell", { name: /SYN-Código, linha 7/ }));
    await user.keyboard("{Enter}");
    expect(ops.applyOperation).not.toHaveBeenCalled();
  });

  it("Enter com a célula focada abre a edição", async () => {
    const user = userEvent.setup();
    renderCell("00123");
    screen.getByRole("cell", { name: /SYN-Código, linha 7/ }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox", { name: "Editar SYN-Código da linha 7" })).toHaveValue("00123");
  });

  it("valor desconhecido aparece como desconhecido, e não como vazio", () => {
    renderCell(null);
    expect(screen.getByText("∅ desconhecido")).toBeInTheDocument();
    expect(screen.queryByText("(vazio)")).not.toBeInTheDocument();
  });
});
