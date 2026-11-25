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
  await page.waitForFunction(() => Object.keys(document.querySelector("form") ?? {}).some((k) => k.startsWith("__reactProps")));
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

test("junção com chave composta N:M exige confirmação antes de criar a tabela", async ({ page }) => {
  await importAndOpen(page, "SYN-procv-busca.csv", "SYN-procv-busca");
  await importAndOpen(page, "SYN-procv-consulta.csv", "SYN-procv-consulta");
  await page.getByRole("tab", { name: "Cruzar tabelas" }).click();
  await page.getByRole("tab", { name: "Junção" }).click();
  const juncao = page.getByRole("tabpanel", { name: "Junção" });

  await juncao.locator("#jn-right").selectOption({ label: "SYN-procv-busca" });
  await juncao.locator("#jn-lk-0").selectOption("Código");
  await juncao.locator("#jn-rk-0").selectOption("Código");
  await juncao.getByRole("button", { name: "Adicionar chave" }).click();
  await juncao.locator("#jn-lk-1").selectOption("Unidade");
  await juncao.locator("#jn-rk-1").selectOption("Unidade");

  await juncao.getByRole("button", { name: "Calcular prévia da junção" }).click();
  const estimativas = juncao.getByRole("region", { name: "Estimativas da junção" });
  await expect(estimativas).toContainText("Cardinalidade: N:M");
  await expect(estimativas).toContainText("Linhas estimadas no resultado");

  // Sem confirmação do crescimento, a criação fica bloqueada.
  const criar = juncao.getByRole("button", { name: "Criar tabela derivada" });
  await expect(criar).toBeDisabled();
  await juncao.getByRole("checkbox", { name: /Confirmo a junção N:M/ }).check();
  await expect(criar).toBeEnabled();

  await criar.click();
  await expect(page.getByRole("status").filter({ hasText: "Tabela derivada" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "As tabelas de origem não foram alteradas." })).toBeVisible();
});
