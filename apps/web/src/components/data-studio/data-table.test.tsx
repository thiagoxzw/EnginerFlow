import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DataTable } from "@/components/data-studio/data-table";
import * as rowsLib from "@/lib/rows";

vi.mock("@/lib/rows", async () => {
  const actual = await vi.importActual<typeof import("@/lib/rows")>("@/lib/rows");
  return { ...actual, queryRows: vi.fn() };
});

const PAGE: rowsLib.RowsPage = {
  total: 3,
  offset: 0,
  limit: 50,
  columns: ["SYN-Código", "Qtd"],
  rows: [
    { row_number: 2, values: ["00123", "10"] },
    { row_number: 3, values: ["0123", ""] },
    { row_number: 4, values: ["AB1", null] },
  ],
};

function renderTable() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DataTable datasetId="ds-1" columns={["SYN-Código", "Qtd"]} />
    </QueryClientProvider>,
  );
}

describe("DataTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(rowsLib.queryRows).mockResolvedValue(PAGE);
  });

  it("distingue vazio e desconhecido e preserva o código com zero à esquerda", async () => {
    renderTable();
    expect(await screen.findByText("00123")).toBeInTheDocument();
    expect(screen.getByText("(vazio)")).toBeInTheDocument();
    expect(screen.getByText("∅ desconhecido")).toBeInTheDocument();
    expect(screen.getByText("0123")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Linhas 1–3 de 3");
  });

  it("aplica um filtro completo e reconsulta o servidor com ele", async () => {
    const user = userEvent.setup();
    renderTable();
    await screen.findByText("00123");

    await user.click(screen.getByRole("button", { name: "Adicionar filtro" }));
    await user.type(screen.getByLabelText("Valor do filtro 1"), "00123");

    await waitFor(() =>
      expect(rowsLib.queryRows).toHaveBeenLastCalledWith(
        "ds-1",
        expect.objectContaining({
          filters: [{ column: "SYN-Código", op: "eq", value: "00123" }],
        }),
      ),
    );
  });

  it("ordena pelo cabeçalho em ciclo asc, desc e sem ordenação", async () => {
    const user = userEvent.setup();
    renderTable();
    const header = (await screen.findByText("Qtd")).closest("th");
    expect(header).toHaveAttribute("aria-sort", "none");

    await user.click(within(header as HTMLElement).getByRole("button"));
    await waitFor(() =>
      expect(rowsLib.queryRows).toHaveBeenLastCalledWith(
        "ds-1",
        expect.objectContaining({ sort: "Qtd", dir: "asc" }),
      ),
    );
    await user.click(within(header as HTMLElement).getByRole("button"));
    await waitFor(() =>
      expect(rowsLib.queryRows).toHaveBeenLastCalledWith(
        "ds-1",
        expect.objectContaining({ sort: "Qtd", dir: "desc" }),
      ),
    );
  });
});
