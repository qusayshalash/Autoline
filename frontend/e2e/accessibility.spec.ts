import { expect, test, type Page } from "@playwright/test";
import { ADMIN, requireCredentials, signIn } from "./helpers";

test.beforeAll(() => requireCredentials(ADMIN, "admin"));

/**
 * A name is read out instead of the control, not alongside it.
 *
 * The static guard in backend/tests/test_accessible_names.py catches a name written in
 * English in the source and a name that resolves to a whole paragraph of translation.
 * What it cannot see is a name bound to a variable - `aria-label={text}` - which is the
 * exact shape the settings help buttons had: every one of them announced its entire
 * explanation where the word "help" belonged. That only shows once the page is running.
 */
const MAX_NAME_LENGTH = 70;

/** Pages that between them render every naming pattern the app has. The settings
 *  sections are separate entries because the page shows one at a time, and the help
 *  buttons - the ones this is really about - live in four of them. */
const PAGES = [
  "/",
  "/admin",
  "/admin/users",
  "/admin/roles",
  "/admin/languages",
  "/admin/files",
  "/admin/activity",
  ...["overview", "storage", "backups", "maintenance", "logs", "security", "system"].map(
    (section) => `/admin/settings?section=${section}`
  ),
];

async function longNames(page: Page) {
  return page.$$eval("[aria-label]", (nodes, limit) =>
    nodes
      .map((n) => ({
        name: (n.getAttribute("aria-label") ?? "").trim(),
        tag: n.tagName.toLowerCase(),
        cls: n.className?.toString().slice(0, 40) ?? "",
      }))
      .filter((n) => n.name.length > limit)
      .map((n) => `<${n.tag} class="${n.cls}"> ${n.name.slice(0, 80)}… (${n.name.length} chars)`),
    MAX_NAME_LENGTH
  );
}

async function namelessControls(page: Page) {
  return page.$$eval("input, select, textarea", (nodes) =>
    nodes
      .filter((n) => {
        const el = n as HTMLInputElement;
        if (el.type === "hidden" || el.type === "file") return false;
        if (el.getAttribute("aria-label")?.trim()) return false;
        if (el.getAttribute("aria-labelledby")) return false;
        if (el.getAttribute("placeholder")?.trim()) return false;
        if (el.getAttribute("title")?.trim()) return false;
        if (el.closest("label")) return false;
        if (el.id && document.querySelector(`label[for="${el.id}"]`)) return false;
        return true;
      })
      .map((n) => `<${n.tagName.toLowerCase()} class="${n.className}">`)
  );
}

test.describe("Accessible names", () => {
  test("no control is announced as a paragraph, and none as nothing", async ({ page }) => {
    await signIn(page, ADMIN);

    for (const path of PAGES) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      expect(await longNames(page), `${path}: names long enough to be read as prose`).toEqual([]);
      expect(await namelessControls(page), `${path}: controls with no name`).toEqual([]);
    }
  });

  test("the settings help buttons say 'help' and describe themselves separately", async ({
    page,
  }) => {
    await signIn(page, ADMIN);
    // maintenance carries two of them; the overview section carries none
    await page.goto("/admin/settings?section=maintenance");
    await page.waitForLoadState("networkidle");

    const hints = page.locator("button.set-hint");
    expect(await hints.count(), "the settings pages should carry help buttons").toBeGreaterThan(0);

    const first = hints.first();
    await expect(first).toHaveAttribute("aria-label", "شرح");
    await expect(first).toHaveAttribute("aria-expanded", "false");

    // Opening it puts the explanation in a description, which is announced after the
    // name rather than instead of it. Hover, not click: the bubble opens on hover, and
    // a click arrives with the pointer already over the button, so it toggles shut.
    await first.hover();
    await expect(first).toHaveAttribute("aria-expanded", "true");
    const describedBy = await first.getAttribute("aria-describedby");
    expect(describedBy, "the open bubble should be the button's description").toBeTruthy();
    // useId produces ":r1:", which is not a valid selector unescaped
    const bubble = page.locator(`[id="${describedBy}"]`);
    await expect(bubble).toBeVisible();
    expect((await bubble.innerText()).length).toBeGreaterThan(MAX_NAME_LENGTH);
  });

  test("the drawer's close button is written in the page's language", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/roles");
    await page.locator(".role-card").first().click();

    const drawer = page.locator(".drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("button", { name: "إغلاق" })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Close" })).toHaveCount(0);
  });

  test("the permission grid names its checkboxes, not its database keys", async ({ page }) => {
    await signIn(page, ADMIN);
    await page.goto("/admin/roles");
    await page.locator(".role-card").first().click();

    const matrix = page.locator(".perm-matrix");
    await expect(matrix).toBeVisible();
    // "datasets.delete" was what a screen reader used to read here
    expect(
      await matrix.locator('input[type=checkbox]').evaluateAll((boxes) =>
        boxes.map((b) => b.getAttribute("aria-label") ?? "").filter((n) => /^[a-z_]+\.[a-z_]+$/.test(n))
      ),
      "checkboxes named with a permission key"
    ).toEqual([]);
  });
});
