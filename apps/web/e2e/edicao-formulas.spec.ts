import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

// Somente dados sintéticos (SYN-*). Credenciais de teste vêm do ambiente local.
const EMAIL = process.env.E2E_EMAIL ?? "";
const PASSWORD = process.env.E2E_PASSWORD ?? "";
const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

async function login(page: Page) {
  await page.goto("/login");
  // Espera o React hidratar antes de preencher: evita clique antes do formulário estar ativo.
  await page.waitForLoadState("networkidle");
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page).toHaveURL(/\/$/);
}

async function importAndOpen(page: Page, file: string, name: string) {
  await page.goto("/data-studio");
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles(fixture(file));
  await page.getByRole("button", { name: "Importar" }).click();
  await page
    .getByRole("listitem")
    .filter({ has: page.getByText(name, { exact: true }) })
    .getByRole("button", { name: "Abrir" })
    .click();
  await expect(page.getByRole("region", { name: "Dados" })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("editar uma célula por duplo clique e desfazer a alteração", async ({ page }) => {
  await importAndOpen(page, "SYN-procv-busca.csv", "SYN-procv-busca");
  // Linhas do fixture: 2 parafuso, 3 parafuso duplicado, 4 arruela, 5 arruela alternativa.
  const celula = page.getByRole("cell", { name: "Descrição, linha 5" });
  await expect(celula).toContainText("SYN arruela alternativa");

  await celula.dblclick();
  const campo = page.getByRole("textbox", { name: "Editar Descrição da linha 5" });
  await campo.fill("SYN arruela editada");
  await campo.press("Enter");
  await expect(page.getByRole("cell", { name: "Descrição, linha 5" })).toContainText("SYN arruela editada");

  await page.getByRole("button", { name: "Desfazer (Ctrl+Z)" }).click();
  await expect(page.getByRole("cell", { name: "Descrição, linha 5" })).toContainText("SYN arruela alternativa");
});

test("Escape cancela a edição sem alterar a célula", async ({ page }) => {
  await importAndOpen(page, "SYN-procv-busca.csv", "SYN-procv-busca");
  const celula = page.getByRole("cell", { name: "Descrição, linha 4" });
  await celula.dblclick();
  const campo = page.getByRole("textbox", { name: "Editar Descrição da linha 4" });
  await campo.fill("NÃO DEVE GRAVAR");
  await campo.press("Escape");
  await expect(page.getByRole("cell", { name: "Descrição, linha 4" })).toContainText("SYN arruela");
  await expect(page.getByText("NÃO DEVE GRAVAR")).toHaveCount(0);
});

test("colar duas células é uma única operação e desfazer reverte as duas", async ({ page }) => {
  await importAndOpen(page, "SYN-procv-busca.csv", "SYN-procv-busca");
  const destino = page.getByRole("cell", { name: "Descrição, linha 2" });
  await destino.focus();
  await destino.evaluate((el) => {
    const dados = new DataTransfer();
    dados.setData("text/plain", "Colado A\nColado B\n");
    el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dados, bubbles: true, cancelable: true }));
  });
  await expect(page.getByRole("cell", { name: "Descrição, linha 2" })).toContainText("Colado A");
  await expect(page.getByRole("cell", { name: "Descrição, linha 3" })).toContainText("Colado B");
  await expect(page.getByRole("status").filter({ hasText: "Uma única operação" })).toBeVisible();

  await page.getByRole("button", { name: "Desfazer (Ctrl+Z)" }).click();
  await expect(page.getByRole("cell", { name: "Descrição, linha 2" })).toContainText("SYN parafuso");
  await expect(page.getByRole("cell", { name: "Descrição, linha 3" })).toContainText("SYN parafuso duplicado");
});

test("fórmula [Qtd]*2 cria tabela derivada rastreável e mostra erros explícitos", async ({ page }) => {
  await importAndOpen(page, "SYN-procv-consulta.csv", "SYN-procv-consulta");
  await page.getByRole("tab", { name: "Fórmulas" }).click();
  const painel = page.getByRole("tabpanel", { name: "Fórmulas" });
  await painel.getByLabel("Fórmula").fill("[Qtd]*2");
  await painel.getByLabel("Nome da nova coluna").fill("Dobro");
  await painel.getByRole("button", { name: "Gerar prévia" }).click();
  await expect(painel.getByText(/Erros explícitos nas linhas: 0 de 5/)).toBeVisible();

  await painel.getByRole("button", { name: "Criar tabela com a coluna calculada" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Tabela derivada" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Rastreabilidade" })).toBeVisible();
});
