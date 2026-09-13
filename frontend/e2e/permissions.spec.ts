import { expect, test } from "@playwright/test";
import { ADMIN, API, VIEWER, requireCredentials, signIn } from "./helpers";

test.beforeAll(() => {
  requireCredentials(ADMIN, "admin");
  requireCredentials(VIEWER, "viewer");
});

test.describe("Roles and permissions", () => {
  test("a viewer sees no upload, rename or delete controls", async ({ page }) => {
    await signIn(page, VIEWER);
    await page.goto("/");
    await expect(page.getByText("الملفات").first()).toBeVisible();

    await expect(page.getByText("رفع ملف CSV")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "حذف" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "إعادة تسمية" })).toHaveCount(0);
  });

  test("a viewer reaching an admin page they lack rights for gets the forbidden screen", async ({
    page,
  }) => {
    await signIn(page, VIEWER);
    await page.goto("/admin/users");
    await expect(page).toHaveURL(/\/forbidden/);
    await expect(page.getByText(/ليس لديك صلاحية/)).toBeVisible();
    // and nothing about other accounts leaked onto the page
    await expect(page.getByText(ADMIN.user)).toHaveCount(0);
  });

  test("hiding a button is not the protection: the API refuses the viewer too", async ({
    request,
  }) => {
    const login = await request.post(`${API}/auth/login`, {
      data: { username: VIEWER.user, password: VIEWER.pass },
    });
    expect(login.status()).toBe(200);

    const ghost = "00000000000000000000000000000000";
    const forbidden: Array<[string, () => Promise<{ status(): number }>]> = [
      ["upload", () => request.post(`${API}/datasets/upload`, { multipart: {
        file: { name: "QA_TEST_x.csv", mimeType: "text/csv", buffer: Buffer.from("a,b\n1,2\n") } } })],
      ["delete dataset", () => request.delete(`${API}/datasets/${ghost}`)],
      ["rename dataset", () => request.patch(`${API}/datasets/${ghost}`, { data: { name: "x.csv" } })],
      ["clean dataset", () => request.post(`${API}/datasets/${ghost}/clean`, { data: { dedupe: true } })],
      ["list users", () => request.get(`${API}/users`)],
      ["create user", () => request.post(`${API}/users`, {
        data: { username: "QA_TEST_ESCALATE", password: "abcdef1", role: "admin" } })],
      ["create role", () => request.post(`${API}/roles`, {
        data: { name: "QA Escalate", permissions: ["system.manage"] } })],
      ["system settings", () => request.get(`${API}/admin/system`)],
      ["activity log", () => request.get(`${API}/admin/activity`)],
      ["start backup", () => request.post(`${API}/admin/backups`, { data: {} })],
    ];

    for (const [label, call] of forbidden) {
      const res = await call();
      expect(res.status(), `viewer must be refused: ${label}`).toBe(403);
    }
  });

  test("a viewer cannot widen their own role", async ({ request }) => {
    await request.post(`${API}/auth/login`, {
      data: { username: VIEWER.user, password: VIEWER.pass },
    });
    const me = await (await request.get(`${API}/auth/me`)).json();

    const promote = await request.patch(`${API}/users/${me.id}`, { data: { role: "super_admin" } });
    expect(promote.status()).toBe(403);

    const widen = await request.patch(`${API}/roles/viewer`, {
      data: { permissions: ["datasets.view", "datasets.delete"] },
    });
    expect(widen.status()).toBe(403);

    const after = await (await request.get(`${API}/auth/me`)).json();
    expect(after.role, "role must be unchanged").toBe(me.role);
  });

  test("built-in roles and the last administrator are protected", async ({ request }) => {
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });

    expect((await request.delete(`${API}/roles/super_admin`)).status()).toBe(409);
    expect(
      (await request.patch(`${API}/roles/super_admin`, { data: { permissions: ["datasets.view"] } })).status()
    ).toBe(409);
    expect((await request.patch(`${API}/roles/viewer`, { data: { name: "Renamed" } })).status()).toBe(409);
  });
});
