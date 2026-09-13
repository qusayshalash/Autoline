import { expect, test } from "@playwright/test";
import { ADMIN, API, requireCredentials, signIn, signOut } from "./helpers";

test.beforeAll(() => requireCredentials(ADMIN, "admin"));

test.describe("Authentication", () => {
  test("signs in with valid credentials and lands on the files page", async ({ page }) => {
    await signIn(page, ADMIN);
    await expect(page).toHaveURL(/\/$|\/admin/);
    await expect(page.getByRole("link", { name: "الملفات" })).toBeVisible();
  });

  test("refuses a wrong password and says so without naming which half was wrong", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.locator("#login-identifier").fill(ADMIN.user);
    await page.locator("#login-password").fill("definitely-the-wrong-password");
    await page.locator('button[type="submit"]').click();

    const error = page.locator(".login-error, [role=alert]").first();
    await expect(error).toBeVisible();
    await expect(page.locator("#login-password")).toBeVisible();
    await expect(error).not.toContainText(ADMIN.user);
  });

  test("will not submit an empty form", async ({ page }) => {
    let posted = false;
    page.on("request", (r) => {
      if (r.url().includes("/auth/login") && r.method() === "POST") posted = true;
    });
    await page.goto("/login");
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(700);
    expect(posted, "an empty form must not reach the server").toBe(false);
  });

  test("sets an HttpOnly session cookie that script cannot read", async ({ page, context }) => {
    await signIn(page, ADMIN);
    const cookie = (await context.cookies()).find((c) => c.name === "access_token");
    expect(cookie, "a session cookie should be set").toBeTruthy();
    expect(cookie!.httpOnly, "session cookie must be HttpOnly").toBe(true);
    expect(await page.evaluate(() => document.cookie)).not.toContain("access_token");
  });

  test("sends an unauthenticated visitor from a deep link to the login page", async ({ page }) => {
    await page.goto("/admin/settings");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator("#login-password")).toBeVisible();
  });

  test("signs out, and the back button does not bring the data back", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/users");
    await expect(page.getByRole("table")).toBeVisible();

    // the sign-out control lives on the main shell, not the admin sidebar
    await page.goto("/");
    await signOut(page);
    await page.goBack();

    await expect(page.locator("#login-password")).toBeVisible();
    await expect(page.getByRole("table")).toHaveCount(0);
  });

  test("the API refuses every protected endpoint without a session", async ({ request }) => {
    for (const path of ["/auth/me", "/datasets", "/users", "/roles", "/admin/overview"]) {
      const res = await request.get(`${API}${path}`);
      expect(res.status(), `${path} while anonymous`).toBe(401);
    }
  });

  test("the API rejects a tampered session token", async ({ request }) => {
    const res = await request.get(`${API}/auth/me`, {
      headers: { Cookie: "access_token=eyJhbGciOiJub25lIn0.eyJzdWIiOiJhZG1pbiJ9." },
    });
    expect(res.status()).toBe(401);
  });
});
