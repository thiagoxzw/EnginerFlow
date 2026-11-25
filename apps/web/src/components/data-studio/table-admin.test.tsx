import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DeletedTablesSection, TableAdminSection } from "@/components/data-studio/table-admin";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("TableAdminSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("só habilita a exclusão com o nome exato e então chama a rota de exclusão lógica", async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch).mockResolvedValue({});
    const onDeleted = vi.fn();
    render(wrap(<TableAdminSection datasetId="ds-1" name="SYN-Peças" onDeleted={onDeleted} />));

    const button = screen.getByRole("button", { name: "Excluir tabela" });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Confirmar nome para excluir"), "SYN-Peça");
    expect(button).toBeDisabled(); // quase igual não basta
    await user.type(screen.getByLabelText("Confirmar nome para excluir"), "s");
    expect(button).toBeEnabled();

    await user.click(button);
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(apiFetch).toHaveBeenCalledWith(
      "/api/v1/datasets/ds-1",
      expect.objectContaining({ method: "DELETE", body: JSON.stringify({ confirm_name: "SYN-Peças" }) }),
    );
  });

  it("renomear envia o novo nome e mostra erro do servidor quando já existe", async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch).mockRejectedValue(new Error("Já existe uma tabela ativa com este nome."));
    render(wrap(<TableAdminSection datasetId="ds-1" name="A" onDeleted={vi.fn()} />));

    await user.clear(screen.getByLabelText("Nome"));
    await user.type(screen.getByLabelText("Nome"), "B");
    await user.click(screen.getByRole("button", { name: "Renomear" }));

    expect(apiFetch).toHaveBeenCalledWith(
      "/api/v1/datasets/ds-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ name: "B" }) }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Já existe uma tabela ativa");
  });
});

describe("DeletedTablesSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lista tabelas excluídas e restaura pela rota de restauração", async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch).mockImplementation(async (path: string) => {
      if (path === "/api/v1/datasets?deleted=true") {
        return [{ id: "ds-9", name: "SYN-Antiga" }];
      }
      return {};
    });
    render(wrap(<DeletedTablesSection />));

    await user.click(await screen.findByRole("button", { name: "Restaurar SYN-Antiga" }));
    expect(apiFetch).toHaveBeenCalledWith(
      "/api/v1/datasets/ds-9/restore",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Tabela restaurada.");
  });
});
