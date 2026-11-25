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

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("inspeção não cria tabelas e falha parcial não impede as demais importações", async ({ page }) => {
  await page.goto("/data-studio");

  // Arquivo binário com extensão CSV: a leitura prévia falha, os outros seguem na fila.
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles([
    fixture("SYN-procv-busca.csv"),
    fixture("SYN-binario.csv"),
  ]);

  const falha = page.getByRole("listitem").filter({ hasText: "SYN-binario.csv" });
  await expect(falha.getByRole("alert")).toContainText("Não foi possível ler o arquivo");

  // Só o arquivo válido entra na importação.
  await expect(page.getByRole("button", { name: "Importar 1 tabela(s)" })).toBeEnabled();
  await page.getByRole("button", { name: "Importar 1 tabela(s)" }).click();
  await expect(page.getByRole("status").filter({ hasText: "1 de 1 importação(ões) concluída(s)." })).toBeVisible();

  // Nenhuma tabela foi criada para o arquivo que falhou na leitura.
  await expect(
    page.getByRole("listitem").filter({ hasText: "SYN-binario" }).getByRole("button", { name: "Abrir" }),
  ).toHaveCount(0);
});
