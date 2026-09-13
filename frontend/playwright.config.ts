import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end suite for AutoLine Data Studio.
 *
 * These tests sign in as real accounts and write real data, so they must never be
 * pointed at an installation that holds anything you care about. Run them against a
 * throwaway DATA_DIR - see e2e/README.md. Everything they create is named QA_TEST_*
 * so it can be identified and removed afterwards.
 *
 * Credentials come from the environment, never from this file:
 *   QA_ADMIN_USER / QA_ADMIN_PASS    an account holding every permission
 *   QA_VIEWER_USER / QA_VIEWER_PASS  an account holding only datasets.view
 */
export default defineConfig({
  testDir: "./e2e",
  // The suite shares one backend and one catalog; running files in parallel would have
  // them deleting each other's rows mid-assertion.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.QA_BASE_URL ?? "http://localhost:5173",
    locale: "ar",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
