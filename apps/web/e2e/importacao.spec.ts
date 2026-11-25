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

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("arrastar e soltar um CSV coloca o arquivo na fila e importa", async ({ page }) => {
  await page.goto("/data-studio");
  const dt = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(new File(["Código;Qtd\n00777;3\n"], "SYN-arrastado.csv", { type: "text/csv" }));
    return data;
  });
  await page.getByText("Arraste arquivos CSV ou XLSX aqui").dispatchEvent("drop", { dataTransfer: dt });

  const item = page.getByRole("listitem").filter({ has: page.getByText("SYN-arrastado.csv", { exact: true }) });
  await expect(item).toBeVisible();
  await page.getByRole("button", { name: "Importar 1 tabela(s)" }).click();
  await expect(page.getByRole("status").filter({ hasText: "SYN-arrastado" }).first()).toBeVisible();
});

test("vários arquivos, abas do XLSX e formato recusado: contagem e resumo corretos", async ({ page }) => {
  await page.goto("/data-studio");
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles([
    fixture("SYN-procv-busca.csv"),
    fixture("SYN-multiabas.xlsx"),
    fixture("SYN-nota.txt"),
  ]);

  await expect(
    page.getByRole("status").filter({ hasText: "Ignorado (formato não suportado): SYN-nota.txt" }),
  ).toBeVisible();

  // Abas: a primeira vem marcada; marcar a segunda vira outra tabela.
  const planilha = page
    .getByRole("listitem")
    .filter({ has: page.getByText("SYN-multiabas.xlsx", { exact: true }) });
  await expect(planilha.getByRole("checkbox", { name: "Rev A" })).toBeChecked();
  await expect(planilha.getByRole("checkbox", { name: "Rev B" })).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Importar 2 tabela(s)" })).toBeEnabled();
  await planilha.getByRole("checkbox", { name: "Rev B" }).check();
  await expect(page.getByRole("button", { name: "Importar 3 tabela(s)" })).toBeEnabled();

  await page.getByRole("button", { name: "Importar 3 tabela(s)" }).click();
  await expect(page.getByRole("status").filter({ hasText: "3 de 3 importação(ões) concluída(s)." })).toBeVisible();
});
