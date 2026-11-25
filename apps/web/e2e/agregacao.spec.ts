import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

// Somente dados sintéticos (SYN-*). Credenciais de teste vêm do ambiente local.
const EMAIL = process.env.E2E_EMAIL ?? "";
const PASSWORD = process.env.E2E_PASSWORD ?? "";
const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

async function login(page: Page) {
  await page.goto("/login");
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

test("agregação por unidade: contagem de códigos, prévia exata e tabela derivada", async ({ page }) => {
  // SYN-procv-busca: PC tem 3 linhas (00123 duas vezes, AB1 uma vez); CX tem 1 linha (AB1).
  await importAndOpen(page, "SYN-procv-busca.csv", "SYN-procv-busca");
  await page.locator("summary", { hasText: "Agrupar e agregar" }).click();
  const agregacao = page.locator("details", { hasText: "Agrupar e agregar" });

  await agregacao.getByRole("checkbox", { name: "Unidade" }).check();
  await agregacao.getByRole("button", { name: "Gerar prévia" }).click();

  await expect(agregacao.getByText("2 grupo(s) a partir de 4 linha(s).")).toBeVisible();
  const linhaPC = agregacao.getByRole("row").filter({ hasText: "PC" });
  await expect(linhaPC).toContainText("3");

  await agregacao.getByRole("button", { name: "Criar tabela derivada" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Tabela derivada" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "As tabelas de origem não foram alteradas." })).toBeVisible();
});
