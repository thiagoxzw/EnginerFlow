import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StructureMenu } from "@/components/data-studio/structure-menu";

describe("menu contextual da tabela", () => {
  it("executa o item escolhido e fecha o menu", () => {
    const run = vi.fn();
    const onClose = vi.fn();
    render(
      <StructureMenu
        x={10}
        y={20}
        label="Linha 3"
        items={[{ label: "Duplicar linha", run }]}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Duplicar linha" }));
    expect(run).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalled();
  });

  it("fecha com Escape sem executar nenhum item", () => {
    const run = vi.fn();
    const onClose = vi.fn();
    render(
      <StructureMenu
        x={0}
        y={0}
        label="Coluna Qtd"
        items={[{ label: "Excluir coluna", run, danger: true }]}
        onClose={onClose}
      />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
    expect(run).not.toHaveBeenCalled();
  });
});
