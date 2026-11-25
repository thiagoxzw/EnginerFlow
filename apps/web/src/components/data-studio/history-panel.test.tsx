import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HistoryPanel, historyShortcut, isEditingField } from "@/components/data-studio/history-panel";
import { ApiError } from "@/lib/api";
import * as ops from "@/lib/operations";
import * as templates from "@/lib/templates";

vi.mock("@/lib/operations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/operations")>("@/lib/operations");
  return {
    ...actual,
    listOperations: vi.fn(),
    listVersions: vi.fn(),
    moveHistory: vi.fn(),
  };
});
vi.mock("@/lib/templates", async () => {
  const actual = await vi.importActual<typeof import("@/lib/templates")>("@/lib/templates");
  return { ...actual, getDatasetState: vi.fn() };
});

const STATE = { dataVersionId: "v-2", metadataVersionId: "m-2" };

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <HistoryPanel datasetId="ds-1" />
    </QueryClientProvider>,
  );
}

describe("historyShortcut", () => {
  it("mapeia Ctrl+Z, Ctrl+Y e Ctrl+Shift+Z e ignora outras teclas", () => {
    const k = (init: KeyboardEventInit) => new KeyboardEvent("keydown", init);
    expect(historyShortcut(k({ key: "z", ctrlKey: true }))).toBe("undo");
    expect(historyShortcut(k({ key: "y", ctrlKey: true }))).toBe("redo");
    expect(historyShortcut(k({ key: "Z", ctrlKey: true, shiftKey: true }))).toBe("redo");
    expect(historyShortcut(k({ key: "z" }))).toBeNull();
    expect(historyShortcut(k({ key: "a", ctrlKey: true }))).toBeNull();
  });

  it("não captura atalho quando o foco está em campo de texto", () => {
    const input = document.createElement("input");
    const div = document.createElement("div");
    expect(isEditingField(input)).toBe(true);
    expect(isEditingField(div)).toBe(false);
  });
});

describe("HistoryPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(templates.getDatasetState).mockResolvedValue(STATE);
    vi.mocked(ops.listOperations).mockResolvedValue([
      { id: "o1", seq: 1, code: "replace_text", code_version: 2, status: "applied", rows_affected: 2, cells_changed: 2, created_at: "" },
      { id: "o2", seq: 2, code: "delete_rows", code_version: 1, status: "undone", rows_affected: 1, cells_changed: 0, created_at: "" },
    ]);
    vi.mocked(ops.listVersions).mockResolvedValue([
      { id: "v-2", number: 2, row_count: 3, content_sha256: "x", created_at: "", is_current: true },
    ]);
    vi.mocked(ops.moveHistory).mockResolvedValue({ current_version_id: "v-1", current_metadata_version_id: "m-1" });
  });

  it("desfaz pelo botão com o estado atual e lista operações com status", async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText(/#1 Substituir texto/)).toBeInTheDocument();
    expect(screen.getByText(/#2 Excluir linhas/)).toHaveTextContent("desfeita");
    expect(screen.getByText("Versão atual: 2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Desfazer (Ctrl+Z)" }));
    await waitFor(() => expect(ops.moveHistory).toHaveBeenCalledWith("ds-1", "undo", STATE));
    expect(await screen.findByRole("status")).toHaveTextContent("Operação desfeita.");
  });

  it("atalho Ctrl+Y refaz quando não há foco em campo de texto", async () => {
    renderPanel();
    await screen.findByText(/#1 Substituir texto/);
    fireEvent.keyDown(window, { key: "y", ctrlKey: true });
    await waitFor(() => expect(ops.moveHistory).toHaveBeenCalledWith("ds-1", "redo", STATE));
  });

  it("conflito 409 orienta a atualizar em vez de mostrar erro bruto", async () => {
    const user = userEvent.setup();
    vi.mocked(ops.moveHistory).mockRejectedValue(new ApiError(409, null));
    renderPanel();
    await screen.findByText(/#1 Substituir texto/);

    await user.click(screen.getByRole("button", { name: "Desfazer (Ctrl+Z)" }));
    expect(await screen.findByRole("status")).toHaveTextContent("A tabela mudou em outra sessão");
  });
});
