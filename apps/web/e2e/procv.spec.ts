import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

// Somente dados sintéticos (arquivos SYN-*). Credenciais de teste vêm do ambiente local.
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

/** Importa (ou reaproveita, se já importado) e abre a tabela pelo botão da lista. */
async function importAndOpen(page: Page, file: string, name: string) {
  await page.goto("/data-studio");
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles(fixture(file));
  await page.getByRole("button", { name: "Importar" }).click();
  await expect(page.getByRole("status").filter({ hasText: /importad|já estava/ })).toBeVisible();
  // Nome exato: "SYN-protheus-produtos" também casa com a derivada "SYN-protheus-produtos × …".
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

test("PROCV com chave composta: prévia, contagens, zeros preservados, exportação e tabela derivada", async ({
  page,
}) => {
  await importAndOpen(page, "SYN-estoque-componentes.csv", "SYN-estoque-componentes");
  await importAndOpen(page, "SYN-protheus-produtos.csv", "SYN-protheus-produtos");
  await page.locator("summary", { hasText: "Cruzar com outra tabela (PROCV)" }).click();
  const procv = page.locator("details", { hasText: "Cruzar com outra tabela (PROCV)" });

  // Sem tabela de busca, a prévia não pode ser gerada.
  await expect(procv.getByRole("button", { name: "Gerar prévia" })).toBeDisabled();

  await procv.locator("#sp-right").selectOption({ label: "SYN-estoque-componentes" });
  await procv.locator("#sp-lk-0").selectOption("B1_COD");
  await procv.locator("#sp-rk-0").selectOption("Código");
  await procv.getByRole("button", { name: "Adicionar chave" }).click();
  await procv.locator("#sp-lk-1").selectOption("B1_UM");
  await procv.locator("#sp-rk-1").selectOption("Unidade");
  await procv.getByRole("checkbox", { name: "Saldo" }).check();

  await procv.getByRole("button", { name: "Gerar prévia" }).click();
  const contagens = procv.getByRole("list", { name: "Contagens da prévia" });
  await expect(contagens).toContainText("Encontrados");
  await expect(contagens).toContainText("Linhas no resultado");

  // Zeros à esquerda da chave preservados na prévia.
  await expect(procv.getByRole("table").getByText("000123", { exact: true }).first()).toBeVisible();

  // Exportação CSV baixa um arquivo.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    procv.getByRole("button", { name: "Exportar CSV" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);

  // Criação da tabela derivada: a origem continua intacta e a derivada aparece na lista.
  await procv.getByRole("button", { name: "Criar tabela derivada" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Tabela derivada" })).toBeVisible();
  await expect(
    page.getByRole("listitem").filter({ hasText: "SYN-protheus-produtos" }).first(),
  ).toBeVisible();
});

test("chave inválida: tabela de busca sem coluna escolhida mantém o botão desabilitado", async ({
  page,
}) => {
  await importAndOpen(page, "SYN-estoque-componentes.csv", "SYN-estoque-componentes");
  await importAndOpen(page, "SYN-protheus-produtos.csv", "SYN-protheus-produtos");
  await page.locator("summary", { hasText: "Cruzar com outra tabela (PROCV)" }).click();
  const procv = page.locator("details", { hasText: "Cruzar com outra tabela (PROCV)" });
  await procv.locator("#sp-right").selectOption({ label: "SYN-estoque-componentes" });
  await procv.locator("#sp-lk-0").selectOption("B1_COD");
  // Sem a coluna da busca escolhida, a prévia não é enviada.
  await expect(procv.getByRole("button", { name: "Gerar prévia" })).toBeDisabled();
});
