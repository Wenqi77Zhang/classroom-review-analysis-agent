import { resolve } from "node:path";

import { defineConfig } from "@playwright/test";

const authStatePath = resolve(
  process.cwd(),
  "test-results/e2e-auth-state.json",
);

export default defineConfig({
  testDir: "tests/e2e",
  globalSetup: "./tests/e2e/global-setup.ts",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: "line",
  projects: [
    { name: "desktop-1550", use: { viewport: { width: 1550, height: 1200 } } },
    { name: "compact-1024", use: { viewport: { width: 1024, height: 900 } } },
    { name: "tablet-900", use: { viewport: { width: 900, height: 900 } } },
    { name: "mobile-620", use: { viewport: { width: 620, height: 800 } } },
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    channel: process.env.E2E_BROWSER_CHANNEL ?? "msedge",
    storageState: authStatePath,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
