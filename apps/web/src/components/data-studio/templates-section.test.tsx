import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { TemplatesSection, cleanTemplateMapping } from "@/components/data-studio/templates-section";
import * as client from "@/lib/templates";

vi.mock("@/lib/templates", async () => {
  const actual = await vi.importActual<typeof import("@/lib/templates")>("@/lib/templates");
  return {
    ...actual,
    listTemplates: vi.fn(),
    createTemplate: vi.fn(),
    updateTemplate: vi.fn(),
    getDatasetState: vi.fn(),
    previewTemplate: vi.fn(),
    applyPreview: vi.fn(),
  };
});

const TEMPLATE: client.Template = {
  id: "tpl-1",
  name: "Modelo SYN",
  mapping: { code: "SYN-Código", quantity: "Qtd" },
  definition_version: 2,
  updated_at: "2026-11-24T00:00:00Z",
};

const STATE = { dataVersionId: "v-1", metadataVersionId: "m-1" };

function renderSection(onApplied = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <TemplatesSection datasetId="ds-1" onApplied={onApplied} />
    </QueryClientProvider>,
  );
  return { onApplied };
}

describe("cleanTemplateMapping", () => {
  it("omite campos vazios e remove espaços das colunas", () => {
    expect(cleanTemplateMapping({ code: "  SYN-Código ", description: "", unit: "  " })).toEqual({
      code: "SYN-Código",
    });
  });
});

describe("TemplatesSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.listTemplates).mockResolvedValue([TEMPLATE]);
    vi.mocked(client.getDatasetState).mockResolvedValue(STATE);
  });

  it("exige confirmação explícita para aplicação parcial e então aplica a prévia confirmada", async () => {
    const user = userEvent.setup();
    vi.mocked(client.previewTemplate)
      .mockResolvedValueOnce({
        preview_id: null,
        expires_at: null,
        template_id: "tpl-1",
        definition_version: 2,
        missing_fields: { code: "SYN-Código" },
      })
      .mockResolvedValueOnce({
        preview_id: "prev-9",
        expires_at: "2026-11-24T00:15:00Z",
        template_id: "tpl-1",
        definition_version: 2,
        missing_fields: { code: "SYN-Código" },
      });
    vi.mocked(client.applyPreview).mockResolvedValue({});
    const { onApplied } = renderSection();

    await screen.findByRole("option", { name: /Modelo SYN/ });
    await user.selectOptions(screen.getByLabelText("Modelo"), "tpl-1");
    await user.click(screen.getByRole("button", { name: "Pré-visualizar aplicação" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("SYN-Código");
    expect(screen.queryByRole("button", { name: "Aplicar modelo" })).not.toBeInTheDocument();

    const confirmButton = screen.getByRole("button", { name: "Gerar prévia com confirmação" });
    expect(confirmButton).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);

    expect(client.previewTemplate).toHaveBeenLastCalledWith("ds-1", "tpl-1", STATE, true);
    await user.click(await screen.findByRole("button", { name: "Aplicar modelo" }));

    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1));
    expect(client.applyPreview).toHaveBeenCalledWith("ds-1", "prev-9", STATE);
    expect(screen.getByRole("status")).toHaveTextContent("histórico anterior foi preservado");
  });

  it("mostra a versão da definição e erro claro quando a tabela mudou antes de aplicar", async () => {
    const user = userEvent.setup();
    vi.mocked(client.previewTemplate).mockResolvedValue({
      preview_id: "prev-1",
      expires_at: "2026-11-24T00:15:00Z",
      template_id: "tpl-1",
      definition_version: 2,
      missing_fields: {},
    });
    vi.mocked(client.applyPreview).mockRejectedValue(
      new Error("A tabela mudou desde a leitura. Atualize a versão e refaça a prévia."),
    );
    const { onApplied } = renderSection();

    await screen.findByRole("option", { name: /Modelo SYN/ });
    await user.selectOptions(screen.getByLabelText("Modelo"), "tpl-1");
    expect(screen.getByText("Definição atual: v2.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pré-visualizar aplicação" }));
    await user.click(await screen.findByRole("button", { name: "Aplicar modelo" }));

    expect(await screen.findByRole("status")).toHaveTextContent("refaça a prévia");
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("cria um modelo novo com as colunas preenchidas", async () => {
    const user = userEvent.setup();
    vi.mocked(client.createTemplate).mockResolvedValue({ ...TEMPLATE, id: "tpl-2", name: "Novo" });
    renderSection();

    await user.type(await screen.findByLabelText("Nome"), "Novo");
    await user.type(screen.getByLabelText("Quantidade"), "Qtd");
    await user.click(screen.getByRole("button", { name: "Criar modelo" }));

    expect(client.createTemplate).toHaveBeenCalledWith("Novo", { quantity: "Qtd" });
    const status = await screen.findByRole("status");
    expect(within(status).getByText(/Modelo criado/)).toBeInTheDocument();
  });
});
