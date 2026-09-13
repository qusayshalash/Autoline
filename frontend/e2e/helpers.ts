import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const API = process.env.QA_API_URL ?? "http://localhost:8000/api";

export const ADMIN = {
  user: process.env.QA_ADMIN_USER ?? "admin",
  pass: process.env.QA_ADMIN_PASS ?? "",
};
export const VIEWER = {
  user: process.env.QA_VIEWER_USER ?? "qa_viewer",
  pass: process.env.QA_VIEWER_PASS ?? "",
};

export function requireCredentials(who: { user: string; pass: string }, label: string) {
  if (!who.pass) {
    throw new Error(
      `Missing password for ${label}. Set QA_${label.toUpperCase()}_PASS before running the suite.`
    );
  }
}

/** Signs in through the real form, the way a person does. */
export async function signIn(page: Page, who: { user: string; pass: string }) {
  await page.goto("/login");
  await page.locator("#login-identifier").fill(who.user);
  await page.locator("#login-password").fill(who.pass);
  await page.locator('button[type="submit"]').click();
  await expect(page.locator("#login-password")).toHaveCount(0, { timeout: 15_000 });
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await expect(page.locator("#login-password")).toBeVisible();
}

/**
 * Destructive actions use window.confirm, which Playwright dismisses by default -
 * so a delete would silently do nothing and the test would fail for the wrong reason.
 */
export function acceptConfirms(page: Page) {
  page.on("dialog", (d) => d.accept());
}

/** A logged-in API context, for asserting what the server does independently of the UI. */
export async function apiLogin(
  request: APIRequestContext,
  who: { user: string; pass: string }
) {
  const res = await request.post(`${API}/auth/login`, {
    data: { username: who.user, password: who.pass },
  });
  expect(res.status(), "API login should succeed").toBe(200);
  return request;
}

/**
 * Prices deliberately span two to six digits.
 *
 * With equal-width numbers a text sort and a numeric sort produce the same order, so a
 * column stored as VARCHAR looks perfectly sorted and the regression guard passes over
 * the bug. Mixed widths are what separate the two: as text, "1000" comes before "99".
 */
const PRICE_WIDTHS = [99, 850, 7300, 64000, 250000];

export const CSV_FIXTURE = {
  name: "QA_TEST_e2e.csv",
  mimeType: "text/csv",
  buffer: Buffer.from(
    [
      "plate,make,model_year,city,price",
      ...Array.from({ length: 60 }, (_, i) =>
        `${20000 + i},${["Toyota", "Kia", "Hyundai", "مرسيدس"][i % 4]},${
          2000 + (i % 25)
        },${["رام الله", "نابلس", "غزة"][i % 3]},${PRICE_WIDTHS[i % 5] + i}`
      ),
    ].join("\n") + "\n",
    "utf-8"
  ),
};
