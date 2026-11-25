import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RowActions, valueFromMode } from "@/components/data-studio/row-actions";
import * as ops from "@/lib/operations";
import * as templates from "@/lib/templates";

vi.mock("@/lib/operations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/operations")>("@/lib/operations");
  return { ...actual, previewOperation: vi.fn(), applyOperation: vi.fn() };
});
vi.mock("@/lib/templates", async () => {
  const actual = await vi.importActual<typeof import("@/lib/templates")>("@/lib/templates");
  return { ...actual, getDatasetState: vi.fn() };
});

const STATE = { dataVersionId: "v-1", metadataVersionId: "m-1" };

function renderActions(selected: number[], onApplied = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RowActions
        datasetId="ds-1"
        columns={["SYN-Código", "Qtd"]}
        selected={selected}
        scopeLabel="seleção manual"
        onApplied={onApplied}
      />
    </QueryClientProvider>,
  );
  return { onApplied };
}

describe("valueFromMode", () => {
  it("grava desconhecido como null e vazio como string vazia", () => {
    expect(valueFromMode("unknown", "ignorado")).toBeNull();
    expect(valueFromMode("empty", "ignorado")).toBe("");
    expect(valueFromMode("text", "7,5")).toBe("7,5");
  });
});

describe("RowActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(templates.getDatasetState).mockResolvedValue(STATE);
    vi.mocked(ops.previewOperation).mockResolvedValue({
      preview_id: "prev-d",
      expires_at: "2026-11-24T00:15:00Z",
      rows_affected: 2,
      cells_changed: 0,
      before_content_sha256: "a",
      after_content_sha256: "b",
    });
  });

  it("exclusão mostra a contagem da prévia e só aplica após confirmação", async () => {
    const user = userEvent.setup();
    vi.mocked(ops.applyOperation).mockResolvedValue({});
    const { onApplied } = renderActions([2, 3]);

    await user.click(screen.getByRole("button", { name: "Excluir linhas" }));
    expect(ops.previewOperation).toHaveBeenCalledWith(
      "ds-1",
      "delete_rows",
      { row_numbers: [2, 3] },
      STATE,
    );
    expect(await screen.findByText(/Excluir 2 linha\(s\)\?/)).toBeInTheDocument();
    expect(ops.applyOperation).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(ops.applyOperation).toHaveBeenCalledWith("ds-1", "prev-d", STATE));
    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1));
  });

  it("atualizar para desconhecido envia null no lote", async () => {
    const user = userEvent.setup();
    renderActions([4]);

    await user.selectOptions(screen.getByLabelText("Tipo de valor"), "unknown");
    await user.click(screen.getByRole("button", { name: "Atualizar valor" }));
    expect(ops.previewOperation).toHaveBeenCalledWith(
      "ds-1",
      "set_rows_value",
      { row_numbers: [4], column: "SYN-Código", value: null },
      STATE,
    );
  });

  it("sem seleção, as ações ficam desabilitadas", () => {
    renderActions([]);
    expect(screen.getByRole("button", { name: "Excluir linhas" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Atualizar valor" })).toBeDisabled();
  });
});
