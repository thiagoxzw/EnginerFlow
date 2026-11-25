import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HeaderSection } from "@/components/data-studio/header-section";
import * as ops from "@/lib/operations";
import * as templates from "@/lib/templates";

vi.mock("@/lib/operations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/operations")>("@/lib/operations");
  return {
    ...actual,
    rawHead: vi.fn(),
    metadataVersions: vi.fn(),
    previewOperation: vi.fn(),
    applyOperation: vi.fn(),
  };
});
vi.mock("@/lib/templates", async () => {
  const actual = await vi.importActual<typeof import("@/lib/templates")>("@/lib/templates");
  return { ...actual, getDatasetState: vi.fn() };
});

const STATE = { dataVersionId: "v-1", metadataVersionId: "m-1" };

function renderSection() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <HeaderSection datasetId="ds-1" />
    </QueryClientProvider>,
  );
}

describe("HeaderSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(ops.rawHead).mockResolvedValue([
      { row_number: 1, values: ["SYN relatório"] },
      { row_number: 3, values: ["SYN-Código", "Qtd"] },
    ]);
    vi.mocked(ops.metadataVersions).mockResolvedValue([
      { id: "m-1", number: 1, header_row: null, is_current: true },
    ]);
    vi.mocked(templates.getDatasetState).mockResolvedValue(STATE);
  });

  it("gera prévia da linha escolhida, exige confirmação textual e aplica com a prévia", async () => {
    const user = userEvent.setup();
    vi.mocked(ops.previewOperation).mockResolvedValue({
      preview_id: "prev-3",
      expires_at: "2026-11-24T00:15:00Z",
      rows_affected: 2,
      cells_changed: 0,
      before_content_sha256: "a",
      after_content_sha256: "b",
    });
    vi.mocked(ops.applyOperation).mockResolvedValue({});
    renderSection();

    await user.click(await screen.findByRole("button", { name: "Usar a linha 3 como cabeçalho" }));
    expect(screen.getByText(/Reconstruir a tabela usando a linha 3/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));

    expect(ops.previewOperation).toHaveBeenCalledWith("ds-1", "set_header_row", { header_row: 3 }, STATE);
    await user.click(await screen.findByRole("button", { name: "Aplicar cabeçalho" }));

    await waitFor(() => expect(ops.applyOperation).toHaveBeenCalledWith("ds-1", "prev-3", STATE));
    expect(await screen.findByRole("status")).toHaveTextContent("Cabeçalho definido na linha 3");
  });

  it("cancelar a escolha não gera prévia", async () => {
    const user = userEvent.setup();
    renderSection();

    await user.click(await screen.findByRole("button", { name: "Usar a linha 3 como cabeçalho" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(ops.previewOperation).not.toHaveBeenCalled();
    expect(screen.queryByText(/Reconstruir a tabela/)).not.toBeInTheDocument();
  });
});
