import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    // Collect browser console logs
    trace: "on-first-retry",
  },
  // No webServer — we assume backend + frontend are already running
})
