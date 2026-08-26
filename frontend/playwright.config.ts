import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
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
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
