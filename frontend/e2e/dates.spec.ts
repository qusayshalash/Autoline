import { expect, test, type Page } from "@playwright/test";
import { ADMIN, requireCredentials, signIn } from "./helpers";

test.beforeAll(() => requireCredentials(ADMIN, "admin"));

/**
 * What the page actually prints.
 *
 * The static guards in backend/tests/test_date_formatting.py keep the parsing in one
 * module and the timestamps on the wire well formed. Neither can see the result: a date
 * is only wrong once it is text on a screen, and the two shapes that were wrong are
 * recognisable on sight.
 *
 * This file deliberately runs the browser in en-US while holding the app in Arabic,
 * because that gap is the bug. `toLocaleString()` with no argument asks the browser, and
 * the rest of the suite runs with the browser already set to "ar" - so the American date
 * never appears there, and a guard written under that setting passes over the very fault
 * it exists for. An English machine reading the Arabic app is also the ordinary case
 * here, not a contrived one.
 */
test.use({ locale: "en-US" });

/**
 * "2026-09-13 23:03:16", and the ISO form ending in Z: the shapes a machine writes.
 *
 * No trailing word boundary - there is none before the Z in "…:33Z", which is exactly
 * what the API now sends and therefore exactly what a raw render would show.
 */
const RAW_DATABASE = /\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}/;

/** "9/13/2026" - month first, which no language this app ships puts first. */
const AMERICAN = /\b(?:[1-9]|1[0-2])\/(?:[1-9]|[12]\d|3[01])\/\d{4}\b/;

const PAGES = [
  "/admin",
  "/admin/users",
  "/admin/roles",
  "/admin/files",
  "/admin/activity",
  "/admin/settings?section=overview",
  "/admin/settings?section=backups",
  "/admin/settings?section=logs",
  "/admin/settings?section=system",
];

/**
 * The app's language is i18next's, not the browser's.
 *
 * Pinned here so the en-US browser above cannot drag the interface into English with
 * it - the point is an Arabic page on an English machine, not an English page.
 */
async function holdArabic(page: Page) {
  await page.addInitScript(() => window.localStorage.setItem("i18nextLng", "ar"));
}

/** Visible text, plus the tooltips - a title attribute is read by a person too. */
async function shownText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const titles = [...document.querySelectorAll("[title]")]
      .map((n) => n.getAttribute("title") ?? "")
      .join("\n");
    return `${document.body.innerText}\n${titles}`;
  });
}

test.describe("Dates", () => {
  test("no screen shows a database timestamp or an American date", async ({ page }) => {
    await holdArabic(page);
    await signIn(page, ADMIN);

    for (const path of PAGES) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const text = await shownText(page);

      expect(text.match(RAW_DATABASE)?.[0], `${path}: a raw database timestamp`).toBeUndefined();
      expect(
        text.match(AMERICAN)?.[0],
        `${path}: a month-first date on an Arabic page`
      ).toBeUndefined();
    }
  });

  test("the system panel shows when the server started, in the page's language", async ({
    page,
  }) => {
    await holdArabic(page);
    await signIn(page, ADMIN);
    await page.goto("/admin/settings?section=system");
    await page.waitForLoadState("networkidle");

    // the value used to arrive as "2026-09-13 23:03:16" and go straight to the screen
    const facts = await page.locator("dl").first().innerText();
    expect(facts).not.toMatch(RAW_DATABASE);
    // Arabic writes the day first, with its own separator between the parts
    expect(facts).toMatch(/\d{1,2}[‏/]{1,2}\d{1,2}[‏/]{1,2}\d{4}/);
  });

  test("the activity log says how long ago, and the exact moment on hover", async ({ page }) => {
    await holdArabic(page);
    await signIn(page, ADMIN);
    await page.goto("/admin/activity");
    await page.waitForLoadState("networkidle");

    const first = page.locator("time.activity-time").first();
    await expect(first).toBeVisible();

    // the cell is the relative reading
    const shown = (await first.innerText()).trim();
    expect(shown, "the cell should read as a phrase, not a timestamp").not.toMatch(RAW_DATABASE);

    // the tooltip is the precise one, and keeps its seconds: two entries a few seconds
    // apart are the difference between one action and two
    const exact = await first.getAttribute("title");
    expect(exact).toBeTruthy();
    expect(exact!, "the log's tooltip keeps the seconds").toMatch(/\d{1,2}:\d{2}:\d{2}/);
  });
});
