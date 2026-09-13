import { expect, test } from "@playwright/test";
import { ADMIN, API, acceptConfirms, requireCredentials, signIn } from "./helpers";

test.beforeAll(() => requireCredentials(ADMIN, "admin"));

const TEST_USER = "QA_TEST_USER_E2E";

test.describe("Administration", () => {
  test("creates, inspects and deletes a user through the interface", async ({ page, request }) => {
    acceptConfirms(page);
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });
    // start clean, in case a previous run stopped half way
    for (const u of await (await request.get(`${API}/users`)).json()) {
      if (u.username === TEST_USER) await request.delete(`${API}/users/${u.id}`);
    }

    await signIn(page, ADMIN);
    await page.goto("/admin/users");
    await page.getByRole("button", { name: "إضافة مستخدم" }).click();

    const dialog = page.locator("dialog, [role=dialog]").last();
    await expect(dialog).toBeVisible();
    const boxes = dialog.locator('input:not([type=checkbox])');
    await boxes.nth(0).fill("QA Test User E2E");
    await boxes.nth(1).fill("qa-e2e@qa.test");
    await boxes.nth(2).fill(TEST_USER);
    await boxes.nth(3).fill("QaE2e!2026#pass");
    await dialog.getByRole("button", { name: "إنشاء مستخدم" }).click();

    await expect(page.getByText(TEST_USER)).toBeVisible();
    const created = (await (await request.get(`${API}/users`)).json()).find(
      (u: { username: string }) => u.username === TEST_USER
    );
    expect(created, "the account should exist on the server too").toBeTruthy();

    // a duplicate username is refused, and the dialog stays open to say so
    await page.getByRole("button", { name: "إضافة مستخدم" }).click();
    const again = page.locator("dialog, [role=dialog]").last();
    const againBoxes = again.locator('input:not([type=checkbox])');
    await againBoxes.nth(2).fill(TEST_USER);
    await againBoxes.nth(3).fill("QaE2e!2026#other");
    await again.getByRole("button", { name: "إنشاء مستخدم" }).click();
    await expect(again, "the dialog must stay open on a conflict").toBeVisible();

    await page.reload();
    await page.getByRole("button", { name: "QA Test User E2E" }).click();
    const drawer = page.locator("dialog, [role=dialog]").last();
    await expect(drawer.getByText(TEST_USER)).toBeVisible();

    await drawer.getByRole("button", { name: "حذف" }).click();
    await expect(page.getByText(TEST_USER)).toHaveCount(0);

    const stillThere = (await (await request.get(`${API}/users`)).json()).find(
      (u: { username: string }) => u.username === TEST_USER
    );
    expect(stillThere, "the account should be gone from the server").toBeUndefined();
  });

  test("every admin section loads without a console error", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => {
      // A 401 on /auth/me before sign-in is expected and logged by the browser itself.
      if (m.type() === "error" && !m.text().includes("401")) errors.push(m.text());
    });

    await signIn(page, ADMIN);
    for (const path of [
      "/admin",
      "/admin/users",
      "/admin/roles",
      "/admin/languages",
      "/admin/files",
      "/admin/activity",
      "/admin/settings",
    ]) {
      await page.goto(path);
      await expect(page.locator("main, .admin-content").first()).toBeVisible();
      await expect(page.getByText(/Cannot read|undefined is not|TypeError/)).toHaveCount(0);
    }
    expect(errors, "no page should log an unexpected error").toEqual([]);
  });

  test("settings sections are linkable and survive a reload", async ({ page }) => {
    await signIn(page, ADMIN);
    for (const section of ["storage", "backups", "maintenance", "logs", "security", "system"]) {
      await page.goto(`/admin/settings?section=${section}`);
      await expect(page.locator(".admin-content, main").first()).toBeVisible();
      await page.reload();
      await expect(page).toHaveURL(new RegExp(`section=${section}`));
    }
  });

  test("the activity log renders translated action names, not raw keys", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/activity");
    await expect(page.getByText("سجل النشاط").first()).toBeVisible();

    // Regression guard: an action without a translation shows its key verbatim.
    const body = await page.locator("body").innerText();
    const rawKeys = [
      "dataset.renamed",
      "activity.purged",
      "housekeeping.swept",
      "housekeeping.retention_changed",
    ].filter((k) => body.includes(k));
    expect(rawKeys, "untranslated action keys are visible in the log").toEqual([]);
  });

  test("the administrator can reach the system status endpoints", async ({ request }) => {
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });
    for (const path of [
      "/admin/overview",
      "/admin/system",
      "/admin/storage",
      "/admin/backups/summary",
      "/admin/housekeeping",
      "/admin/lockouts",
    ]) {
      expect((await request.get(`${API}${path}`)).status(), path).toBe(200);
    }
  });

  test("the activity trim refuses a horizon below the one-week floor", async ({ request }) => {
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });
    expect((await request.post(`${API}/admin/activity/purge`, { data: { older_than_days: 0 } })).status()).toBe(422);
    expect((await request.post(`${API}/admin/activity/purge`, { data: { older_than_days: 1 } })).status()).toBe(422);

    const safe = await request.post(`${API}/admin/activity/purge`, { data: { older_than_days: 3650 } });
    expect(safe.status()).toBe(200);
    expect((await safe.json()).removed, "nothing is that old").toBe(0);
  });
});
