import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

// Somente dados sintéticos (arquivos SYN-*). Credenciais de teste vêm do ambiente local.
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
  await page.getByRole("tab", { name: "Cruzar tabelas" }).click();
  await page.getByRole("tab", { name: "Super-PROCV" }).click();
  const procv = page.getByRole("tabpanel", { name: "Super-PROCV" });

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
  await page.getByRole("tab", { name: "Cruzar tabelas" }).click();
  await page.getByRole("tab", { name: "Super-PROCV" }).click();
  const procv = page.getByRole("tabpanel", { name: "Super-PROCV" });
  await procv.locator("#sp-right").selectOption({ label: "SYN-estoque-componentes" });
  await procv.locator("#sp-lk-0").selectOption("B1_COD");
  // Sem a coluna da busca escolhida, a prévia não é enviada.
  await expect(procv.getByRole("button", { name: "Gerar prévia" })).toBeDisabled();
});

test("duplicidades, chave vazia e zeros: contagens exatas, política de erro e exportação XLSX", async ({
  page,
}) => {
  // Consulta: 00123/PC (x2) tem duas correspondências; 0123/PC não existe; a linha 3 tem chave vazia.
  // Busca: 00123/PC duplicado; AB1/CX e AB1/PC distintos. Chave composta: Código + Unidade.
  await importAndOpen(page, "SYN-procv-busca.csv", "SYN-procv-busca");
  await importAndOpen(page, "SYN-procv-consulta.csv", "SYN-procv-consulta");
  await page.getByRole("tab", { name: "Cruzar tabelas" }).click();
  await page.getByRole("tab", { name: "Super-PROCV" }).click();
  const procv = page.getByRole("tabpanel", { name: "Super-PROCV" });

  await procv.locator("#sp-right").selectOption({ label: "SYN-procv-busca" });
  await procv.locator("#sp-lk-0").selectOption("Código");
  await procv.locator("#sp-rk-0").selectOption("Código");
  await procv.getByRole("button", { name: "Adicionar chave" }).click();
  await procv.locator("#sp-lk-1").selectOption("Unidade");
  await procv.locator("#sp-rk-1").selectOption("Unidade");
  await procv.getByRole("checkbox", { name: "Descrição" }).check();

  // Política "Recusar a operação": duplicidade deve gerar erro compreensível, sem prévia.
  await procv.locator("#sp-dup").selectOption("error");
  await procv.getByRole("button", { name: "Gerar prévia" }).click();
  await expect(procv.getByRole("alert")).toContainText("múltiplas correspondências");

  // Volta à política padrão: contagens exatas.
  await procv.locator("#sp-dup").selectOption("first");
  await procv.getByRole("button", { name: "Gerar prévia" }).click();
  const contagens = procv.getByRole("list", { name: "Contagens da prévia" });
  await expect(contagens).toContainText("Encontrados: 1");
  await expect(contagens).toContainText("Não encontrados: 1");
  await expect(contagens).toContainText("Com múltiplas correspondências: 2");
  await expect(contagens).toContainText("Chave inválida (vazia ou desconhecida): 1");
  await expect(contagens).toContainText("Linhas no resultado: 5");

  // Zeros à esquerda preservados e chave composta legível na amostra de não encontrados.
  await expect(procv.getByText("00123", { exact: true }).first()).toBeVisible();
  await expect(
    procv.getByText("Chaves não encontradas (amostra): 0123 + PC", { exact: true }),
  ).toBeVisible();

  // Exportação XLSX.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    procv.getByRole("button", { name: "Exportar XLSX" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
});
