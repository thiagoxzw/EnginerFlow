import { defineConfig, devices } from "@playwright/test";

// Os servidores (API e web) são iniciados pelo CI ou manualmente. Não sobe nada automaticamente:
// a API precisa de PostgreSQL. Ver docs/operations/FASE_2B2_STATUS.md.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
