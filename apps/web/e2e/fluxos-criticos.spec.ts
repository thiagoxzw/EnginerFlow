import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

// Dados exclusivamente sintéticos. Credenciais de teste vêm do ambiente do CI.
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

/** Importa o arquivo e abre a tabela pelo botão do item da lista. */
async function importAndOpen(page: Page, file: string, name: string) {
  await page.goto("/data-studio");
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles(fixture(file));
  await page.getByRole("button", { name: "Importar" }).click();
  await page
    .getByRole("listitem")
    .filter({ hasText: name })
    .getByRole("button", { name: "Abrir" })
    .click();
  await expect(page.getByRole("region", { name: "Dados" })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("modelo com colunas ausentes exige confirmação antes de aplicar parcialmente", async ({
  page,
}) => {
  await importAndOpen(page, "SYN-tpl.csv", "SYN-tpl");
  const modelos = page.getByRole("region", { name: "Modelos de mapeamento" });

  // Cria modelo com uma coluna que não existe na tabela.
  await modelos.locator("#tpl-name").fill("Modelo parcial");
  await modelos.locator("#tpl-code").fill("SYN-Código");
  await modelos.locator("#tpl-unit").fill("Unidade-inexistente");
  await modelos.getByRole("button", { name: "Criar modelo" }).click();
  await expect(modelos.getByRole("status")).toContainText("Modelo criado");

  // Seleciona o modelo e pré-visualiza: a coluna ausente aparece e não há aplicação ainda.
  await modelos.locator("#tpl-select").selectOption({ label: "Modelo parcial (v1)" });
  await modelos.getByRole("button", { name: "Pré-visualizar aplicação" }).click();
  await expect(modelos.getByRole("alert")).toContainText("Unidade-inexistente");
  await expect(modelos.getByRole("button", { name: "Aplicar modelo" })).toHaveCount(0);

  // Sem confirmação, a prévia com confirmação fica desabilitada.
  const gerar = modelos.getByRole("button", { name: "Gerar prévia com confirmação" });
  await expect(gerar).toBeDisabled();
  await modelos.getByRole("checkbox", { name: /Confirmo a aplicação parcial/ }).check();
  await gerar.click();

  await modelos.getByRole("button", { name: "Aplicar modelo" }).click();
  await expect(modelos.getByRole("status")).toContainText("histórico anterior foi preservado");
});

test("seleção manual de cabeçalho reconstrói a tabela a partir do original", async ({ page }) => {
  await importAndOpen(page, "SYN-cab.csv", "SYN-cab");
  const cabecalho = page.getByRole("region", { name: "Cabeçalho" });

  await cabecalho.getByRole("button", { name: "Usar a linha 2 como cabeçalho" }).click();
  await cabecalho.getByRole("button", { name: "Gerar prévia" }).click();
  await cabecalho.getByRole("button", { name: "Aplicar cabeçalho" }).click();
  await expect(cabecalho.getByRole("status")).toContainText("Cabeçalho definido na linha 2");
  // Cabeçalho da tabela de dados (não as opções dos selects, que ficam ocultas).
  await expect(
    page.getByRole("region", { name: "Dados" }).getByRole("button", { name: "SYN-Código", exact: true }),
  ).toBeVisible();
});

test("exclusão e desfazer de linhas selecionadas", async ({ page }) => {
  await importAndOpen(page, "SYN-del.csv", "SYN-del");
  // Linha 2 do arquivo é SYN-020 (o cabeçalho ocupa a linha 1).
  await page.getByRole("checkbox", { name: "Selecionar linha 2" }).check();
  const acoes = page.getByRole("region", { name: "Ações nas linhas selecionadas" });
  await acoes.getByRole("button", { name: "Excluir linhas" }).click();
  await acoes.getByRole("button", { name: "Confirmar" }).click();
  await expect(acoes.getByRole("status")).toContainText("Linhas excluídas logicamente");
  await expect(page.getByText("SYN-020", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Desfazer (Ctrl+Z)" }).click();
  await expect(page.getByText("Operação desfeita.")).toBeVisible();
  await expect(page.getByText("SYN-020", { exact: true })).toBeVisible();
});

test("excluir e restaurar tabela com confirmação do nome exato", async ({ page }) => {
  await importAndOpen(page, "SYN-del.csv", "SYN-del");
  const gerenciar = page.getByRole("region", { name: "Gerenciar tabela" });
  const excluir = gerenciar.getByRole("button", { name: "Excluir tabela" });
  await expect(excluir).toBeDisabled();
  await gerenciar.getByLabel("Confirmar nome para excluir").fill("SYN-del");
  await excluir.click();

  const excluidas = page.getByRole("region", { name: "Tabelas excluídas" });
  await expect(excluidas.getByRole("button", { name: "Restaurar SYN-del" })).toBeVisible();
  await excluidas.getByRole("button", { name: "Restaurar SYN-del" }).click();
  await expect(excluidas.getByRole("status")).toContainText("Tabela restaurada.");
});

test("aplicação com prévia obsoleta mostra conflito de versão", async ({ browser }) => {
  // Duas abas da mesma sessão: a segunda aplica uma mudança enquanto a primeira tem prévia.
  const context = await browser.newContext();
  const a = await context.newPage();
  const b = await context.newPage();
  await login(a);
  await importAndOpen(a, "SYN-conf.csv", "SYN-conf");
  await b.goto("/data-studio");
  await b.getByRole("listitem").filter({ hasText: "SYN-conf" }).getByRole("button", { name: "Abrir" }).click();
  await expect(b.getByRole("region", { name: "Dados" })).toBeVisible();

  const substituirA = a.getByRole("region", { name: "Localizar e substituir" });
  const substituirB = b.getByRole("region", { name: "Localizar e substituir" });
  // A prepara uma substituição e a mantém pendente.
  await substituirA.getByRole("checkbox", { name: "SYN-Descrição" }).check();
  await substituirA.getByLabel("Localizar").fill("Tinta");
  await substituirA.getByLabel("Substituir por").fill("Tinta X");
  await substituirA.getByRole("button", { name: "Gerar prévia" }).click();
  await expect(substituirA.getByRole("button", { name: "Aplicar substituição" })).toBeVisible();

  // B altera a tabela primeiro.
  await substituirB.getByRole("checkbox", { name: "Qtd" }).check();
  await substituirB.getByLabel("Localizar").fill("5");
  await substituirB.getByLabel("Substituir por").fill("50");
  await substituirB.getByRole("button", { name: "Gerar prévia" }).click();
  await substituirB.getByRole("button", { name: "Aplicar substituição" }).click();
  await expect(substituirB.getByRole("status")).toContainText("Substituição aplicada");

  // A aplica a prévia antiga: deve ser recusada com orientação, sem alterar nada.
  await substituirA.getByRole("button", { name: "Aplicar substituição" }).click();
  await expect(a.getByText(/A tabela mudou/)).toBeVisible();
  await context.close();
});
