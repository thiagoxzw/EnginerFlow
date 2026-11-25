import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReplaceSection, buildReplaceParams } from "@/components/data-studio/replace-section";
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
const COLUMNS = ["SYN-Código", "SYN-Descrição", "Qtd"];

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ReplaceSection datasetId="ds-1" columns={COLUMNS} />
    </QueryClientProvider>,
  );
}

describe("buildReplaceParams", () => {
  const base = {
    columns: ["SYN-Descrição"],
    find: "M8",
    replace: "M-8",
    matchCase: true,
    wholeCell: false,
    filterColumn: "Qtd",
    filterOp: "" as const,
    filterValue: "",
  };

  it("omite filtro sem operador e exige valor para operadores que o pedem", () => {
    expect(buildReplaceParams(base)).not.toHaveProperty("filters");
    expect(buildReplaceParams({ ...base, filterOp: "gt", filterValue: " " })).not.toHaveProperty(
      "filters",
    );
    expect(buildReplaceParams({ ...base, filterOp: "gt", filterValue: "5" })).toHaveProperty(
      "filters",
      [{ column: "Qtd", op: "gt", value: "5" }],
    );
    expect(buildReplaceParams({ ...base, filterOp: "is_empty" })).toHaveProperty("filters", [
      { column: "Qtd", op: "is_empty" },
    ]);
  });
});

describe("ReplaceSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(templates.getDatasetState).mockResolvedValue(STATE);
  });

  it("gera prévia com contagens antes de permitir aplicar", async () => {
    const user = userEvent.setup();
    vi.mocked(ops.previewOperation).mockResolvedValue({
      preview_id: "prev-7",
      expires_at: "2026-11-24T00:15:00Z",
      rows_affected: 3,
      cells_changed: 3,
      before_content_sha256: "a",
      after_content_sha256: "b",
    });
    vi.mocked(ops.applyOperation).mockResolvedValue({});
    renderSection();

    expect(screen.getByRole("button", { name: "Gerar prévia" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "SYN-Descrição" }));
    await user.type(screen.getByLabelText("Localizar"), "M8");
    await user.type(screen.getByLabelText("Substituir por"), "M-8");
    expect(screen.queryByRole("button", { name: "Aplicar substituição" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));
    expect(ops.previewOperation).toHaveBeenCalledWith(
      "ds-1",
      "replace_text",
      {
        columns: ["SYN-Descrição"],
        find: "M8",
        replace: "M-8",
        match_case: true,
        whole_cell: false,
      },
      STATE,
    );
    expect(await screen.findByRole("status")).toHaveTextContent("3 linha(s) e 3 célula(s)");

    await user.click(screen.getByRole("button", { name: "Aplicar substituição" }));
    await waitFor(() => expect(ops.applyOperation).toHaveBeenCalledWith("ds-1", "prev-7", STATE));
  });

  it("alterar o texto invalida a prévia anterior", async () => {
    const user = userEvent.setup();
    vi.mocked(ops.previewOperation).mockResolvedValue({
      preview_id: "prev-8",
      expires_at: "2026-11-24T00:15:00Z",
      rows_affected: 1,
      cells_changed: 1,
      before_content_sha256: "a",
      after_content_sha256: "b",
    });
    renderSection();

    await user.click(screen.getByRole("checkbox", { name: "Qtd" }));
    await user.type(screen.getByLabelText("Localizar"), "1");
    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));
    await screen.findByRole("button", { name: "Aplicar substituição" });

    await user.type(screen.getByLabelText("Localizar"), "0");
    expect(screen.queryByRole("button", { name: "Aplicar substituição" })).not.toBeInTheDocument();
  });

  it("informa quando nada corresponde", async () => {
    const user = userEvent.setup();
    vi.mocked(ops.previewOperation).mockResolvedValue({
      preview_id: "prev-9",
      expires_at: "2026-11-24T00:15:00Z",
      rows_affected: 0,
      cells_changed: 0,
      before_content_sha256: "a",
      after_content_sha256: "a",
    });
    renderSection();

    await user.click(screen.getByRole("checkbox", { name: "Qtd" }));
    await user.type(screen.getByLabelText("Localizar"), "zz");
    await user.click(screen.getByRole("button", { name: "Gerar prévia" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Nada será alterado");
  });
});
