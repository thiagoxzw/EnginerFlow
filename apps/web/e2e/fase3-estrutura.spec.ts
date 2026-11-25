import { expect, test, type Page } from "@playwright/test";

// Somente dados sintéticos gerados no próprio teste (SYN-f3-*). Cada teste importa uma tabela nova,
// com conteúdo único, para não herdar alterações de outro teste. Credenciais vêm do ambiente local.
const EMAIL = process.env.E2E_EMAIL ?? "";
const PASSWORD = process.env.E2E_PASSWORD ?? "";

// Linhas (número exibido): 2 Parafuso/007, 3 Porca/0, 4 Arruela/(vazio), 5 Bucha/4.
// O import deduplica por hash do conteúdo: o código recebe um sufixo único por teste, para que
// cada tabela seja de fato nova. Os valores de descrição e quantidade ficam idênticos.
function csvFor(uid: string): string {
  return `SYN-Código;SYN-Descrição;Qtd\n001-${uid};Parafuso;007\n002-${uid};Porca;0\n003-${uid};Arruela;\n004-${uid};Bucha;4\n`;
}

async function login(page: Page) {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page).toHaveURL(/\/$/);
}

/** Importa uma tabela nova (nome único) e a abre. Retorna o nome. */
async function openFreshTable(page: Page): Promise<string> {
  const uid = `${Date.now()}${Math.floor(Math.random() * 1_000_000)}`;
  const name = `SYN-f3-${uid}`;
  await page.goto("/data-studio");
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles({
    name: `${name}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from(csvFor(uid), "utf8"),
  });
  await page.getByRole("button", { name: "Importar" }).click();
  await page
    .getByRole("listitem")
    .filter({ has: page.getByText(name, { exact: true }) })
    .getByRole("button", { name: "Abrir" })
    .click();
  await expect(page.getByRole("region", { name: "Dados" })).toBeVisible();
  return name;
}

// Toda consulta fica dentro da região "Dados": a página também tem a tabela de prévia do upload.
function grade(page: Page) {
  return page.getByRole("region", { name: "Dados" });
}

function cell(page: Page, column: string, row: number) {
  return grade(page).getByRole("cell", { name: `${column}, linha ${row}`, exact: true });
}

/** Cabeçalho da coluna (o botão de ordenação tem o nome da coluna). */
function header(page: Page, name: string | RegExp) {
  return grade(page)
    .locator("thead th")
    .filter({ has: page.getByRole("button", typeof name === "string" ? { name, exact: true } : { name }) });
}

/** Clique com botão direito no número da linha: segunda célula da linha de dados (após o checkbox). */
async function rowMenu(page: Page, dataRowIndex: number) {
  await grade(page).locator("tbody tr").nth(dataRowIndex).locator("td").nth(1).click({ button: "right" });
}

async function columnMenu(page: Page, name: string | RegExp) {
  await header(page, name).click({ button: "right" });
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("seleção por teclado (Shift+seta) limpa o intervalo em uma operação e Desfazer restaura", async ({ page }) => {
  await openFreshTable(page);
  await cell(page, "SYN-Descrição", 2).click();
  await page.keyboard.press("Shift+ArrowDown");
  await page.keyboard.press("Delete");
  await expect(page.getByRole("status").filter({ hasText: "2 célula(s) limpas" })).toBeVisible();
  await expect(cell(page, "SYN-Descrição", 2)).not.toContainText("Parafuso");
  await expect(cell(page, "SYN-Descrição", 3)).not.toContainText("Porca");

  await page.getByRole("button", { name: "Desfazer (Ctrl+Z)" }).click();
  await expect(cell(page, "SYN-Descrição", 2)).toContainText("Parafuso");
  await expect(cell(page, "SYN-Descrição", 3)).toContainText("Porca");
});

test("inserir linha abaixo renumera na ordem exibida; Desfazer restaura a numeração", async ({ page }) => {
  await openFreshTable(page);
  await rowMenu(page, 0); // linha 2 (Parafuso)
  await page.getByRole("menuitem", { name: "Inserir linha abaixo" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Linha vazia inserida após a linha 2" })).toBeVisible();
  // Porca passa de linha 3 para linha 4; a nova linha 3 fica vazia.
  await expect(cell(page, "SYN-Descrição", 4)).toContainText("Porca");
  await expect(cell(page, "SYN-Descrição", 3)).not.toContainText("Porca");

  await page.getByRole("button", { name: "Desfazer (Ctrl+Z)" }).click();
  await expect(cell(page, "SYN-Descrição", 3)).toContainText("Porca");
});

test("duplicar linha coloca a cópia logo abaixo do original", async ({ page }) => {
  await openFreshTable(page);
  await rowMenu(page, 0);
  await page.getByRole("menuitem", { name: "Duplicar linha" }).click();
  await expect(cell(page, "SYN-Descrição", 2)).toContainText("Parafuso");
  await expect(cell(page, "SYN-Descrição", 3)).toContainText("Parafuso");
  await expect(cell(page, "SYN-Descrição", 4)).toContainText("Porca");
});

test("duplicar e excluir coluna são operações versionadas e desfazíveis", async ({ page }) => {
  await openFreshTable(page);
  await columnMenu(page, /^SYN-Descrição/);
  await page.getByRole("menuitem", { name: "Duplicar coluna" }).click();
  await expect(header(page, /SYN-Descrição \(cópia\)/)).toBeVisible();
  await page.getByRole("button", { name: "Desfazer (Ctrl+Z)" }).click();
  await expect(header(page, /SYN-Descrição \(cópia\)/)).toHaveCount(0);

  await columnMenu(page, /^Qtd/);
  await page.getByRole("menuitem", { name: "Excluir coluna" }).click();
  await page.getByRole("button", { name: "Confirmar exclusão" }).click();
  await expect(header(page, /^Qtd/)).toHaveCount(0);
  await page.getByRole("button", { name: "Desfazer (Ctrl+Z)" }).click();
  await expect(header(page, /^Qtd/)).toBeVisible();
});

test("edição em massa grava um valor em todas as células do intervalo", async ({ page }) => {
  await openFreshTable(page);
  await cell(page, "SYN-Descrição", 2).click();
  await page.keyboard.press("Shift+ArrowDown");
  await page.getByRole("textbox", { name: "Valor para a seleção" }).fill("MASSA");
  await page.getByRole("button", { name: "Aplicar à seleção" }).click();
  await expect(page.getByRole("status").filter({ hasText: "2 célula(s) alteradas" })).toBeVisible();
  await expect(cell(page, "SYN-Descrição", 2)).toContainText("MASSA");
  await expect(cell(page, "SYN-Descrição", 3)).toContainText("MASSA");
});

test("copiar intervalo em TSV e colar texto com tabulação, aspas e quebra de linha", async ({ page }) => {
  await openFreshTable(page);
  await cell(page, "SYN-Descrição", 2).click();
  await page.keyboard.press("Shift+ArrowDown");
  const copied = await cell(page, "SYN-Descrição", 2).evaluate((el) => {
    const dados = new DataTransfer();
    el.dispatchEvent(new ClipboardEvent("copy", { clipboardData: dados, bubbles: true, cancelable: true }));
    return dados.getData("text/plain");
  });
  expect(copied).toBe("Parafuso\nPorca");

  // Excel escreve célula com tabulação e aspas entre aspas, com aspas internas duplicadas.
  const texto = '"com\ttab"\n"com ""aspas"""';
  await cell(page, "SYN-Descrição", 4).evaluate((el, t) => {
    const dados = new DataTransfer();
    dados.setData("text/plain", t);
    el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dados, bubbles: true, cancelable: true }));
  }, texto);
  await expect(cell(page, "SYN-Descrição", 4)).toContainText("com");
  await expect(cell(page, "SYN-Descrição", 5)).toContainText('com "aspas"');
});

test("reordenar colunas persiste após atualizar e não altera células de outras colunas", async ({ page }) => {
  await openFreshTable(page);
  await columnMenu(page, /^SYN-Descrição/);
  await page.getByRole("menuitem", { name: "Mover para a esquerda" }).click();
  const descricaoAntesDoCodigo = async () => {
    const titulos = (await grade(page).locator("thead th").allInnerTexts()).map((t) => t.trim());
    return titulos.findIndex((t) => t.startsWith("SYN-Descrição")) < titulos.findIndex((t) => t.startsWith("SYN-Código"));
  };
  await expect.poll(descricaoAntesDoCodigo).toBe(true);
  // Reordenar não mexe em valores: a célula da coluna Código continua igual.
  await expect(cell(page, "SYN-Código", 2)).toContainText("001");

  await page.reload();
  // A tabela aberta e a ordem voltam após atualizar a página, neste navegador.
  await expect(page.getByRole("region", { name: "Dados" })).toBeVisible();
  await expect.poll(descricaoAntesDoCodigo).toBe(true);
});

test("seleção de linha é descartada após operação estrutural (renumeração)", async ({ page }) => {
  await openFreshTable(page);
  const marcada = page.getByRole("checkbox", { name: "Selecionar linha 2" });
  await marcada.check();
  await expect(marcada).toBeChecked();
  await rowMenu(page, 2); // linha 4
  await page.getByRole("menuitem", { name: "Inserir linha abaixo" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Linha vazia inserida" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Selecionar linha 2" })).not.toBeChecked();
});

test("fórmulas novas: ARRED e SEERRO mostram erros explícitos na prévia", async ({ page }) => {
  await openFreshTable(page);
  await page.getByRole("tab", { name: "Fórmulas" }).click();
  const painel = page.getByRole("tabpanel", { name: "Fórmulas" });
  // Qtd: 007, 0, vazio e 4. Vazio em conta é #VAZIO! (um erro explícito).
  await painel.getByLabel("Fórmula").fill("ARRED([Qtd];0)");
  await painel.getByLabel("Nome da nova coluna").fill("Arred");
  await painel.getByRole("button", { name: "Gerar prévia" }).click();
  await expect(painel.getByText(/Erros explícitos nas linhas: 1 de 4/)).toBeVisible();

  await painel.getByLabel("Fórmula").fill("SEERRO([Qtd];0)");
  await painel.getByRole("button", { name: "Gerar prévia" }).click();
  await expect(painel.getByText(/Erros explícitos nas linhas: 0 de 4/)).toBeVisible();
});
