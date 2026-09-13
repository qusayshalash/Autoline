import { expect, test } from "@playwright/test";
import { ADMIN, API, CSV_FIXTURE, requireCredentials } from "./helpers";

test.beforeAll(() => requireCredentials(ADMIN, "admin"));

let datasetId = "";

/** One dataset, imported once, shared by every assertion in this file. */
test.beforeAll(async ({ request }) => {
  await request.post(`${API}/auth/login`, {
    data: { username: ADMIN.user, password: ADMIN.pass },
  });
  const up = await (
    await request.post(`${API}/datasets/upload`, {
      multipart: { file: { ...CSV_FIXTURE, name: "QA_TEST_grid.csv" } },
    })
  ).json();
  datasetId = up.dataset_id;
  const job = await (
    await request.post(`${API}/datasets/${datasetId}/import`, {
      data: { encoding: up.detected_encoding, delimiter: up.detected_delimiter, has_header: true },
    })
  ).json();
  await expect
    .poll(async () => (await (await request.get(`${API}/jobs/${job.id}`)).json()).status, {
      timeout: 60_000,
    })
    .toBe("done");
});

test.afterAll(async ({ request }) => {
  if (datasetId) await request.delete(`${API}/datasets/${datasetId}`);
});

// `request` is test-scoped: the sign-in done in beforeAll belongs to the worker's own
// context, so each test has to establish its own session or every call comes back 401.
test.beforeEach(async ({ request }) => {
  await request.post(`${API}/auth/login`, {
    data: { username: ADMIN.user, password: ADMIN.pass },
  });
});

async function query(request: any, body: Record<string, unknown>) {
  const res = await request.post(`${API}/datasets/${datasetId}/data`, { data: body });
  expect(res.status()).toBe(200);
  return res.json();
}

test.describe("Data grid", () => {
  test("paginates without repeating or losing rows", async ({ request }) => {
    const first = await query(request, { page: 1, page_size: 25 });
    expect(first.total_rows).toBe(60);
    expect(first.rows).toHaveLength(25);

    const third = await query(request, { page: 3, page_size: 25 });
    expect(third.rows, "the last page holds the remainder").toHaveLength(10);

    const past = await query(request, { page: 99, page_size: 25 });
    expect(past.rows, "a page past the end is empty, not an error").toHaveLength(0);

    const a = await query(request, { page: 1, page_size: 10, sort_by: "plate" });
    const b = await query(request, { page: 2, page_size: 10, sort_by: "plate" });
    const overlap = a.rows.filter((r: unknown[]) =>
      b.rows.some((o: unknown[]) => JSON.stringify(o) === JSON.stringify(r))
    );
    expect(overlap, "consecutive pages must not repeat rows").toHaveLength(0);
  });

  test("caps page_size rather than honouring an absurd value", async ({ request }) => {
    const huge = await query(request, { page: 1, page_size: 999_999 });
    expect(huge.rows.length).toBeLessThanOrEqual(1000);
  });

  test("searches by whole word, partial word, Arabic, and case-insensitively", async ({ request }) => {
    const full = await query(request, { page: 1, page_size: 5, search: "Toyota" });
    expect(full.total_rows).toBeGreaterThan(0);

    const partial = await query(request, { page: 1, page_size: 5, search: "toyo" });
    expect(partial.total_rows).toBeGreaterThanOrEqual(full.total_rows);

    const upper = await query(request, { page: 1, page_size: 5, search: "TOYOTA" });
    expect(upper.total_rows, "search must be case-insensitive").toBe(full.total_rows);

    const arabic = await query(request, { page: 1, page_size: 5, search: "رام الله" });
    expect(arabic.total_rows).toBeGreaterThan(0);

    const none = await query(request, { page: 1, page_size: 5, search: "zzz_no_such_value" });
    expect(none.total_rows, "no matches means zero, not everything").toBe(0);

    const blank = await query(request, { page: 1, page_size: 5, search: "" });
    expect(blank.total_rows, "an empty search returns everything").toBe(60);
  });

  test("treats LIKE wildcards typed by the user as literal characters", async ({ request }) => {
    for (const wildcard of ["%", "_"]) {
      const res = await query(request, { page: 1, page_size: 5, search: wildcard });
      expect(res.total_rows, `'${wildcard}' must not match every row`).not.toBe(60);
    }
  });

  test("filters, and combines filters with search", async ({ request }) => {
    const one = await query(request, {
      page: 1,
      page_size: 5,
      filters: [{ column: "make", op: "eq", value: "Toyota" }],
    });
    expect(one.total_rows).toBeGreaterThan(0);
    expect(one.total_rows).toBeLessThan(60);

    const inverse = await query(request, {
      page: 1,
      page_size: 5,
      filters: [{ column: "make", op: "neq", value: "Toyota" }],
    });
    expect(one.total_rows + inverse.total_rows, "eq and neq must partition the table").toBe(60);

    const two = await query(request, {
      page: 1,
      page_size: 5,
      filters: [
        { column: "make", op: "eq", value: "Toyota" },
        { column: "model_year", op: "gte", value: 2015 },
      ],
    });
    expect(two.total_rows, "a second filter can only narrow").toBeLessThanOrEqual(one.total_rows);
  });

  test("sorts a numeric column by value, not alphabetically", async ({ request }) => {
    // Regression guard. A VARCHAR-backed ORDER BY puts 100446 before 10099 because it
    // compares text; the filter path already casts with TRY_CAST and this must match it.
    const page = await query(request, { page: 1, page_size: 60, sort_by: "price", sort_dir: "asc" });
    const index = page.columns.indexOf("price");
    const values = page.rows.map((r: string[]) => Number(r[index])).filter((n: number) => !Number.isNaN(n));

    expect(values.length).toBeGreaterThan(0);
    expect(values, "ascending sort on a number column must be numeric").toEqual(
      [...values].sort((a, b) => a - b)
    );

    const desc = await query(request, {
      page: 1,
      page_size: 60,
      sort_by: "price",
      sort_dir: "desc",
    });
    const descValues = desc.rows.map((r: string[]) => Number(r[index]));
    expect(descValues).toEqual([...descValues].sort((a, b) => b - a));
  });

  test("refuses an injected column name instead of executing it", async ({ request }) => {
    const before = await request.get(`${API}/users`);
    const userCountBefore = (await before.json()).length;

    for (const column of ['price"; DROP TABLE users--', "no_such_column", "1=1"]) {
      const res = await request.post(`${API}/datasets/${datasetId}/data`, {
        data: { page: 1, page_size: 5, sort_by: column },
      });
      expect([200, 400, 422], `sort_by=${column}`).toContain(res.status());
    }
    for (const column of ['make"; DROP TABLE users--', "no_such_column"]) {
      const res = await request.post(`${API}/datasets/${datasetId}/data`, {
        data: { page: 1, page_size: 5, filters: [{ column, op: "eq", value: "x" }] },
      });
      expect([200, 400, 422], `filter column=${column}`).toContain(res.status());
    }

    const after = await request.get(`${API}/users`);
    expect(after.status(), "the users table must still be there").toBe(200);
    expect((await after.json()).length).toBe(userCountBefore);

    const rows = await query(request, { page: 1, page_size: 1 });
    expect(rows.total_rows, "no rows may be lost to an injection probe").toBe(60);
  });

  test("group-by buckets account for every row", async ({ request }) => {
    const res = await request.post(`${API}/datasets/${datasetId}/group`, {
      data: { column: "make", page: 1, page_size: 100 },
    });
    expect(res.status()).toBe(200);
    const total = (await res.json()).groups.reduce(
      (sum: number, g: { count: number }) => sum + g.count,
      0
    );
    expect(total, "grouped counts must add up to the table total").toBe(60);
  });

  test("stores injected markup as inert text on screen", async ({ page, request }) => {
    const payload = Buffer.from(
      ["note", "<script>window.__xss=1</script>", "<img src=x onerror=window.__xss=2>"].join("\n") + "\n"
    );
    const up = await (
      await request.post(`${API}/datasets/upload`, {
        multipart: { file: { name: "QA_TEST_xss.csv", mimeType: "text/csv", buffer: payload } },
      })
    ).json();
    const job = await (
      await request.post(`${API}/datasets/${up.dataset_id}/import`, {
        data: { encoding: up.detected_encoding, delimiter: up.detected_delimiter, has_header: true },
      })
    ).json();
    await expect
      .poll(async () => (await (await request.get(`${API}/jobs/${job.id}`)).json()).status, {
        timeout: 60_000,
      })
      .toBe("done");

    await page.goto("/login");
    await page.locator("#login-identifier").fill(ADMIN.user);
    await page.locator("#login-password").fill(ADMIN.pass);
    await page.locator('button[type="submit"]').click();
    await expect(page.locator("#login-password")).toHaveCount(0);

    await page.goto(`/datasets/${up.dataset_id}/explore`);
    await expect(page.getByRole("table")).toBeVisible();

    expect(await page.evaluate(() => (window as any).__xss), "no payload may execute").toBeUndefined();
    expect(await page.locator("img[onerror]").count()).toBe(0);
    await expect(page.getByText("<script>window.__xss=1</script>")).toBeVisible();

    await request.delete(`${API}/datasets/${up.dataset_id}`);
  });
});
