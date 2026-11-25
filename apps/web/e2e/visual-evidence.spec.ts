import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

// Evidência visual com dados SINTÉTICOS. Só roda com VISUAL_OUT (diretório de saída) definido.
// VISUAL_LABEL identifica a etapa (ex.: "antes" ou "depois"). Não faz parte da suíte de regressão.
const OUT = process.env.VISUAL_OUT ?? "";
const LABEL = process.env.VISUAL_LABEL ?? "medicao";
const EMAIL = process.env.E2E_EMAIL ?? "";
const PASSWORD = process.env.E2E_PASSWORD ?? "";
const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

const VIEWPORTS = [
  { width: 1920, height: 1080 },
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 390, height: 844 },
];

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

test.skip(!OUT, "Evidência visual: defina VISUAL_OUT.");

test("medições e capturas do Data Studio em quatro resoluções", async ({ page }) => {
  mkdirSync(OUT, { recursive: true });
  await login(page);
  await page.goto("/data-studio");
  await page.getByLabel("Arquivo (.csv ou .xlsx)").setInputFiles(fixture("SYN-procv-busca.csv"));
  await page.getByRole("button", { name: "Importar" }).click();
  await page
    .getByRole("listitem")
    .filter({ has: page.getByText("SYN-procv-busca", { exact: true }) })
    .getByRole("button", { name: "Abrir" })
    .click();
  await expect(page.getByRole("region", { name: "Dados" })).toBeVisible();

  const metrics: Record<string, unknown>[] = [];
  for (const vp of VIEWPORTS) {
    await page.setViewportSize(vp);
    // A tabela aberta não fica na URL: reabre a cada resolução (recarregar a página a fecha).
    await page.goto("/data-studio");
    await page
      .getByRole("listitem")
      .filter({ has: page.getByText("SYN-procv-busca", { exact: true }) })
      .getByRole("button", { name: "Abrir" })
      .click();
    await expect(page.getByRole("region", { name: "Dados" })).toBeVisible();
    const data = page.getByRole("region", { name: "Dados" });
    const m = await page.evaluate(() => ({
      pageScrollWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
      pageHeight: document.documentElement.scrollHeight,
    }));
    const box = await data.boundingBox();
    const row = await page.getByRole("row").nth(1).boundingBox();
    metrics.push({
      label: LABEL,
      viewport: `${vp.width}x${vp.height}`,
      dadosTopoPx: Math.round(box?.y ?? -1),
      primeiraLinhaVisivel: Boolean(row && row.y + row.height <= vp.height),
      overflowHorizontalPagina: m.pageScrollWidth - m.viewportWidth,
      alturaPaginaPx: m.pageHeight,
    });
    const name = `${LABEL}-${vp.width}x${vp.height}`;
    await page.screenshot({ path: join(OUT, `${name}-tela.png`), fullPage: false });
    await page.screenshot({ path: join(OUT, `${name}-completa.png`), fullPage: true });
  }
  writeFileSync(join(OUT, `metricas-${LABEL}.json`), JSON.stringify(metrics, null, 2), "utf8");
});
