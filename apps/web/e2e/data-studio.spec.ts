import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Dados sintéticos apenas. Credenciais de teste vêm do ambiente do CI, nunca do repositório.
const EMAIL = process.env.E2E_EMAIL ?? "";
const PASSWORD = process.env.E2E_PASSWORD ?? "";
// Módulo ES: `__dirname` não existe; o caminho é resolvido a partir de import.meta.url.
const FIXTURE = fileURLToPath(new URL("./fixtures/SYN-e2e.csv", import.meta.url));

test.beforeAll(() => {
  if (!EMAIL || !PASSWORD) {
    throw new Error("Defina E2E_EMAIL e E2E_PASSWORD para o teste de ponta a ponta.");
  }
});

test("importa, filtra, substitui em lote com prévia e desfaz pelo histórico", async ({ page }) => {
  // Login
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page).toHaveURL(/\/$/);

  // Importação
  await page.goto("/data-studio");
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles(FIXTURE);
  await page.getByRole("button", { name: "Importar" }).click();
  await page.getByRole("button", { name: "SYN-e2e" }).click();
  await expect(page.getByRole("region", { name: "Dados" })).toBeVisible();

  // Filtro: quantidade maior que 5 (10 e 7,5; zero não casa)
  await page.getByRole("button", { name: "Adicionar filtro" }).click();
  await page.getByLabel("Operador do filtro 1").selectOption({ label: "maior que" });
  await page.getByLabel("Valor do filtro 1").fill("5");
  await expect(page.getByText(/Linhas 1–2 de 2/)).toBeVisible();

  // Substituição em lote: localizar "Parafuso" e trocar, com prévia obrigatória
  const replace = page.getByRole("region", { name: "Localizar e substituir" });
  await replace.getByRole("checkbox", { name: "SYN-Descrição" }).check();
  await replace.getByLabel("Localizar").fill("Parafuso");
  await replace.getByLabel("Substituir por").fill("Parafuso X");
  await expect(replace.getByRole("button", { name: "Aplicar substituição" })).toHaveCount(0);
  await replace.getByRole("button", { name: "Gerar prévia" }).click();
  await expect(replace.getByText(/1 linha\(s\) e 1 célula\(s\) serão alteradas/)).toBeVisible();
  await replace.getByRole("button", { name: "Aplicar substituição" }).click();
  await expect(page.getByText("Parafuso X")).toBeVisible();

  // Histórico: desfazer restaura o valor original
  await page.getByRole("button", { name: "Desfazer (Ctrl+Z)" }).click();
  await expect(page.getByText("Operação desfeita.")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Parafuso", exact: true })).toBeVisible();
});
