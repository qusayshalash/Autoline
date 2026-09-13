import { expect, test } from "@playwright/test";
import { ADMIN, API, CSV_FIXTURE, cancelDialog, confirmDialog, requireCredentials, signIn } from "./helpers";

test.beforeAll(() => requireCredentials(ADMIN, "admin"));

/**
 * Deleting used to go through window.confirm: a dialog the browser draws left-to-right,
 * with buttons in the operating system's language, that no theme reaches and no test
 * can see. These check the replacement is the app's own.
 */
test.describe("Confirming a deletion", () => {
  let datasetId = "";

  test.beforeEach(async ({ request }) => {
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });
    const up = await (
      await request.post(`${API}/datasets/upload`, {
        multipart: { file: { ...CSV_FIXTURE, name: "QA_TEST_confirm.csv" } },
      })
    ).json();
    datasetId = up.dataset_id;
  });

  test.afterEach(async ({ request }) => {
    if (datasetId) await request.delete(`${API}/datasets/${datasetId}`);
  });

  test("the question is the app's own dialog, not the browser's", async ({ page }) => {
    let nativeDialogs = 0;
    page.on("dialog", (d) => {
      nativeDialogs += 1;
      d.dismiss();
    });

    await signIn(page, ADMIN);
    await page.goto("/");
    const card = page.locator(".dataset-row").filter({ hasText: "QA_TEST_confirm.csv" }).first();
    await card.getByRole("button", { name: "حذف" }).click();

    const dialog = page.locator(".set-dialog");
    await expect(dialog).toBeVisible();
    expect(nativeDialogs, "the browser's own dialog must not appear").toBe(0);

    await expect(dialog).toHaveAttribute("role", "alertdialog");
    await expect(dialog).toContainText("هل أنت متأكد من حذف هذا الملف؟");
    await expect(dialog.getByRole("button", { name: "إلغاء" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "حذف" })).toBeVisible();

    // it reads in the app's direction, which is the whole reason for replacing it
    const direction = await dialog.evaluate((el) => getComputedStyle(el).direction);
    expect(direction).toBe("rtl");

    await cancelDialog(page);
  });

  test("escape closes it and nothing is deleted", async ({ page, request }) => {
    await signIn(page, ADMIN);
    await page.goto("/");
    const card = page.locator(".dataset-row").filter({ hasText: "QA_TEST_confirm.csv" }).first();
    await card.getByRole("button", { name: "حذف" }).click();
    await expect(page.locator(".set-dialog")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.locator(".set-dialog")).toHaveCount(0);

    expect((await request.get(`${API}/datasets/${datasetId}`)).status(), "still there").toBe(200);
  });

  test("cancelling leaves the file alone, confirming removes it", async ({ page, request }) => {
    await signIn(page, ADMIN);
    await page.goto("/");
    const card = page.locator(".dataset-row").filter({ hasText: "QA_TEST_confirm.csv" }).first();

    await card.getByRole("button", { name: "حذف" }).click();
    await cancelDialog(page);
    expect((await request.get(`${API}/datasets/${datasetId}`)).status()).toBe(200);

    await card.getByRole("button", { name: "حذف" }).click();
    await confirmDialog(page);

    await expect
      .poll(async () => (await request.get(`${API}/datasets/${datasetId}`)).status(), {
        timeout: 15_000,
      })
      .toBe(404);
    datasetId = "";
  });
});
