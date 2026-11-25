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

test("comparação por chave composta: idênticos, removidos, adicionados e chaves inválidas", async ({ page }) => {
  // Origem SYN-procv-consulta (5 linhas) e busca SYN-procv-busca (4 linhas), chave Código + Unidade.
  // 00123|PC aparece 2x na origem e 2x na busca; 0123|PC só na origem; AB1|CX nas duas; AB1|PC só na busca;
  // uma linha da origem tem Código vazio.
  await importAndOpen(page, "SYN-procv-busca.csv", "SYN-procv-busca");
  await importAndOpen(page, "SYN-procv-consulta.csv", "SYN-procv-consulta");
  await page.getByRole("tab", { name: "Cruzar tabelas" }).click();
  await page.getByRole("tab", { name: "Comparar", exact: true }).click();
  const comparacao = page.getByRole("tabpanel", { name: "Comparar", exact: true });

  await comparacao.locator("#cp-right").selectOption({ label: "SYN-procv-busca" });
  await comparacao.locator("#cp-lk-0").selectOption("Código");
  await comparacao.locator("#cp-rk-0").selectOption("Código");
  await comparacao.getByRole("button", { name: "Adicionar chave" }).click();
  await comparacao.locator("#cp-lk-1").selectOption("Unidade");
  await comparacao.locator("#cp-rk-1").selectOption("Unidade");
  await comparacao.getByRole("button", { name: "Comparar" }).click();

  const contagens = comparacao.getByRole("list", { name: "Contagens da comparação" });
  await expect(contagens).toContainText("Idênticos: 3");
  await expect(contagens).toContainText("Removidos (só nesta tabela): 1");
  await expect(contagens).toContainText("Adicionados (só na tabela de busca): 1");
  await expect(contagens).toContainText("Chaves repetidas na tabela de busca: 1");
  await expect(contagens).toContainText("Chaves inválidas nesta tabela: 1");

  await comparacao.getByRole("button", { name: "Criar tabela de diferenças" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Tabela derivada" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "As tabelas de origem não foram alteradas." })).toBeVisible();
});
