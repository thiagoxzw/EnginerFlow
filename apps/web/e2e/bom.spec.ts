import { expect, test, type Page } from "@playwright/test";

// Dados sintéticos gerados no próprio teste (BOM-SYN-*). Cada teste usa códigos únicos
// (o import deduplica por conteúdo). Credenciais de teste vêm do ambiente local.
const EMAIL = process.env.E2E_EMAIL ?? "";
const PASSWORD = process.env.E2E_PASSWORD ?? "";

function bomCsv(uid: string, extra = ""): string {
  return [
    "Código pai;Código;Descrição;Qtd;Unidade;Revisão",
    `;ONIBUS-SYN-${uid};Ônibus elétrico sintético;1;UN;A`,
    `ONIBUS-SYN-${uid};CONJ-SYN-TRAC;Conjunto de tração;2;UN;A`,
    `ONIBUS-SYN-${uid};CONJ-SYN-BAT;Conjunto de baterias;1;UN;A`,
    `CONJ-SYN-TRAC;COMP-SYN-MOT;Motor sintético;4;UN;B`,
    `CONJ-SYN-TRAC;PARAF-SYN-M8;Parafuso M8;0,5;KG;`,
    `CONJ-SYN-BAT;COMP-SYN-MOT;Motor sintético;1;UN;B`,
    extra,
  ]
    .filter(Boolean)
    .join("\n");
}

async function login(page: Page) {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.waitForFunction(() => Object.keys(document.querySelector("form") ?? {}).some((k) => k.startsWith("__reactProps")));
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: /entrar/i }).click();
  await expect(page).toHaveURL(/\/$/);
}

/** Importa um CSV pelo Data Studio e devolve o nome da tabela criada. */
async function importTable(page: Page, uid: string, csv: string): Promise<string> {
  const name = `SYN-bom-${uid}`;
  await page.goto("/data-studio");
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles({
    name: `${name}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf8"),
  });
  await page.getByRole("button", { name: "Importar" }).click();
  await expect(page.getByRole("listitem").filter({ has: page.getByText(name, { exact: true }) })).toBeVisible();
  return name;
}

/** Cria a estrutura pelo assistente de importação (mapeamento sugerido e confirmação). */
async function importBom(page: Page, table: string, structure: string) {
  await page.goto("/bom");
  const option = page.locator('select[aria-label="Tabela de origem"] option', { hasText: table }).first();
  const value = await option.getAttribute("value");
  expect(value, `tabela ${table} não aparece na lista de origem`).toBeTruthy();
  await page.getByLabel("Tabela de origem").selectOption(value as string);
  await page.getByLabel("Coluna para Código do conjunto pai").selectOption("Código pai");
  await page.getByLabel("Coluna para Código do componente").selectOption("Código");
  await page.getByLabel("Coluna para Quantidade").selectOption("Qtd");
  await page.getByRole("button", { name: "Gerar prévia" }).click();
  const previa = page.getByRole("region", { name: "Prévia da importação" });
  await expect(previa).toContainText("linhas");
  await page.getByLabel("Nome da estrutura").fill(structure);
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(page.getByText(`Estrutura "${structure}" criada.`)).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("importa uma estrutura com prévia e calcula a explosão por veículo", async ({ page }) => {
  const uid = `${Date.now()}`;
  const table = await importTable(page, uid, bomCsv(uid));
  const structure = `BOM SYN ${uid}`;
  await importBom(page, table, structure);

  await page.getByRole("tab", { name: "Explosão de materiais" }).click();
  await page.getByLabel("Conjunto de topo").selectOption(`ONIBUS-SYN-${uid}`);
  await page.getByLabel("Quantidade de veículos").fill("10");
  await page.getByRole("button", { name: "Explodir" }).click();
  // Motor: 2 tração × 4 + 1 bateria × 1 = 9 por veículo → 90 para 10 veículos.
  const linhaMotor = page.getByRole("row").filter({ hasText: "COMP-SYN-MOT" });
  await expect(linhaMotor).toContainText("90");
  // Parafuso: 0,5 × 2 × 10 = 10 kg.
  await expect(page.getByRole("row").filter({ hasText: "PARAF-SYN-M8" })).toContainText("10");
});

test("editar a quantidade cria nova revisão; desfazer volta à anterior sem apagar nada", async ({ page }) => {
  const uid = `${Date.now()}`;
  const table = await importTable(page, uid, bomCsv(uid));
  const structure = `BOM SYN edit ${uid}`;
  await importBom(page, table, structure);

  await page.getByRole("tab", { name: "Estrutura" }).click();
  await page.getByLabel("Buscar na estrutura").fill("COMP-SYN-MOT");
  await page.getByRole("button", { name: /COMP-SYN-MOT/ }).first().click();
  await page.getByLabel("Nova quantidade").fill("6");
  await page.getByRole("button", { name: "Gravar quantidade" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Quantidade alterada." })).toBeVisible();
  await expect(page.getByText("revisão de trabalho: r2 (atual)")).toBeVisible();

  await page.getByRole("button", { name: "Desfazer (revisão anterior)" }).click();
  await expect(page.getByText("revisão de trabalho: r1 (atual)")).toBeVisible();
  // A revisão 2 continua no histórico.
  await page.getByRole("tab", { name: "Histórico" }).click();
  await expect(page.getByRole("row").filter({ hasText: "r2" })).toBeVisible();
});

test("validação aponta erros de um arquivo com dados inválidos sem alterá-los", async ({ page }) => {
  const uid = `${Date.now()}`;
  const bad = bomCsv(uid, `CONJ-SYN-TRAC;PARAF-SYN-X;Parafuso ruim;abc;UN;`);
  const table = await importTable(page, uid, bad);
  const structure = `BOM SYN erro ${uid}`;
  await importBom(page, table, structure);

  await page.getByRole("tab", { name: "Validação" }).click();
  await page.getByRole("button", { name: "Validar estrutura" }).click();
  await expect(page.getByRole("list", { name: "Inconsistências" })).toContainText("Quantidade inválida: 'abc'");
  await expect(page.getByRole("status").filter({ hasText: /Erros: [1-9]/ })).toBeVisible();
});

test("kit calcula materiais por veículo e lote", async ({ page }) => {
  const uid = `${Date.now()}`;
  const table = await importTable(page, uid, bomCsv(uid));
  const structure = `BOM SYN kit ${uid}`;
  await importBom(page, table, structure);

  await page.getByRole("tab", { name: "Kits" }).click();
  await page.getByLabel("Nome do kit").fill("Kit tração");
  await page.getByLabel("Subconjuntos do kit").fill("CONJ-SYN-TRAC;1");
  await page.getByRole("button", { name: "Salvar kit" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Kit criado." })).toBeVisible();

  await page.getByLabel("Kit para cálculo").selectOption({ label: "Kit tração" });
  await page.getByLabel("Veículos do cálculo").fill("10");
  await page.getByLabel("Lote do cálculo").fill("2");
  await page.getByRole("button", { name: "Calcular" }).click();
  // Motor: 4 por kit × 2 kits × 10 veículos = 80.
  await expect(page.getByRole("row").filter({ hasText: "COMP-SYN-MOT" })).toContainText("80");
});

test("duplicação completa cria códigos provisórios marcados e não altera o original", async ({ page }) => {
  const uid = `${Date.now()}`;
  const extra = [
    `CONJ-SYN-TRAC;SUBI-SYN-${uid};Subconjunto interno;1;UN;`,
    `SUBI-SYN-${uid};FOLHA-SYN-${uid};Componente folha;3;UN;`,
  ].join("\n");
  const table = await importTable(page, uid, bomCsv(uid, extra));
  const structure = `BOM SYN dup ${uid}`;
  await importBom(page, table, structure);

  await page.getByRole("tab", { name: "Estrutura" }).click();
  await page.getByLabel("Buscar na estrutura").fill("CONJ-SYN-TRAC");
  await page.getByRole("button", { name: /CONJ-SYN-TRAC/ }).first().click();
  await page.getByLabel("Novo código do conjunto duplicado").fill(`CONJ-COPIA-${uid}`);
  await page.getByRole("button", { name: "Duplicar conjunto completo" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Conjunto completo duplicado" })).toBeVisible();

  // O subconjunto interno foi copiado com código provisório, marcado na árvore.
  await page.getByLabel("Buscar na estrutura").fill("-CP");
  await expect(page.getByText("provisório").first()).toBeVisible();
  // O original continua com o código oficial.
  await page.getByLabel("Buscar na estrutura").fill(`SUBI-SYN-${uid}`);
  await expect(page.getByRole("button", { name: new RegExp(`SUBI-SYN-${uid}`) }).first()).toBeVisible();
});
