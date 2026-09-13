import { expect, test } from "@playwright/test";
import { ADMIN, API, CSV_FIXTURE, acceptConfirms, requireCredentials, signIn } from "./helpers";

test.beforeAll(() => requireCredentials(ADMIN, "admin"));

/**
 * The product's spine, driven through the API with the UI checked at each step -
 * upload, import, read, rename, export, delete. The UI assertions are what prove the
 * screen reflects the state; the API calls are what make the test deterministic.
 */
test.describe("Dataset lifecycle", () => {
  test("upload -> import -> read -> rename -> export -> delete", async ({ page, request }) => {
    acceptConfirms(page);
    await signIn(page, ADMIN);
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });

    // --- upload -------------------------------------------------------------
    const upload = await request.post(`${API}/datasets/upload`, {
      multipart: { file: CSV_FIXTURE },
    });
    expect(upload.status(), "upload should succeed").toBe(200);
    const meta = await upload.json();
    const id: string = meta.dataset_id;
    expect(meta.columns).toHaveLength(5);
    expect(meta.detected_delimiter).toBe(",");

    // --- import -------------------------------------------------------------
    const started = await request.post(`${API}/datasets/${id}/import`, {
      data: {
        encoding: meta.detected_encoding,
        delimiter: meta.detected_delimiter,
        has_header: true,
      },
    });
    expect(started.status()).toBe(200);
    const job = await started.json();

    await expect
      .poll(
        async () => (await (await request.get(`${API}/jobs/${job.id}`)).json()).status,
        { timeout: 60_000, message: "import job should finish" }
      )
      .toBe("done");

    const row = await (await request.get(`${API}/datasets/${id}`)).json();
    expect(row.row_count_raw, "all 60 rows should land").toBe(60);
    expect(row.status).toBe("ready");

    // --- the file shows up on screen ----------------------------------------
    await page.goto("/");
    await expect(page.getByText(CSV_FIXTURE.name).first()).toBeVisible();

    // --- read it in the explorer --------------------------------------------
    await page.goto(`/datasets/${id}/explore`);
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByText("60").first()).toBeVisible();
    await expect(page.getByText("رام الله").first()).toBeVisible();

    // --- rename -------------------------------------------------------------
    const renamed = "QA_TEST_e2e_renamed.csv";
    const patch = await request.patch(`${API}/datasets/${id}`, { data: { name: renamed } });
    expect(patch.status()).toBe(200);
    expect((await (await request.get(`${API}/datasets/${id}`)).json()).original_filename).toBe(renamed);

    const empty = await request.patch(`${API}/datasets/${id}`, { data: { name: "" } });
    expect(empty.status(), "an empty name must be refused").toBe(422);

    await page.goto("/");
    await expect(page.getByText(renamed).first()).toBeVisible();

    // --- export, in each offered format --------------------------------------
    for (const format of ["csv", "xlsx", "pdf"] as const) {
      const exp = await request.post(`${API}/datasets/${id}/export`, { data: { format } });
      expect(exp.status(), `${format} export should start`).toBe(200);
      const ejob = await exp.json();
      await expect
        .poll(
          async () => (await (await request.get(`${API}/jobs/${ejob.id}`)).json()).status,
          { timeout: 60_000, message: `${format} export should finish` }
        )
        .toBe("done");

      const file = await request.get(`${API}/datasets/${id}/export/${ejob.id}/download`);
      expect(file.status()).toBe(200);
      expect((await file.body()).length, `${format} export should not be empty`).toBeGreaterThan(0);
    }

    // --- delete, and confirm it is really gone --------------------------------
    const del = await request.delete(`${API}/datasets/${id}`);
    expect(del.status()).toBe(200);
    expect((await request.get(`${API}/datasets/${id}`)).status(), "gone after delete").toBe(404);

    await page.goto("/");
    await page.reload();
    await expect(page.getByText(renamed)).toHaveCount(0);
  });

  test("a file with duplicate rows can be de-duplicated, and the count drops", async ({ request }) => {
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });

    const messy = Buffer.from(
      ["plate,make,year", "1,Toyota,2015", "1,Toyota,2015", "2,Kia,2019", "3,Ford,2020"].join("\n") + "\n"
    );
    const up = await (
      await request.post(`${API}/datasets/upload`, {
        multipart: { file: { name: "QA_TEST_dupes.csv", mimeType: "text/csv", buffer: messy } },
      })
    ).json();

    const j = await (
      await request.post(`${API}/datasets/${up.dataset_id}/import`, {
        data: { encoding: up.detected_encoding, delimiter: up.detected_delimiter, has_header: true },
      })
    ).json();
    await expect
      .poll(async () => (await (await request.get(`${API}/jobs/${j.id}`)).json()).status, {
        timeout: 60_000,
      })
      .toBe("done");

    const clean = await request.post(`${API}/datasets/${up.dataset_id}/clean`, {
      data: { dedupe: true },
    });
    expect(clean.status()).toBe(200);
    const result = await clean.json();
    expect(result.duplicates_removed, "the duplicate row should be removed").toBeGreaterThanOrEqual(1);
    expect(result.rows_after).toBeLessThan(result.rows_before);

    await request.delete(`${API}/datasets/${up.dataset_id}`);
  });

  test("odd files are handled without a server error", async ({ request }) => {
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });

    const cases: Array<[string, Buffer]> = [
      ["QA_TEST_headeronly.csv", Buffer.from("a,b,c\n")],
      ["QA_TEST_zero.csv", Buffer.from("")],
      ["QA_TEST_عربي.csv", Buffer.from("لوحة,صانع\n1,تويوتا\n", "utf-8")],
      ["QA_TEST_semi.csv", Buffer.from("﻿a;b\n1;2\n", "utf-8")],
    ];

    for (const [name, buffer] of cases) {
      const res = await request.post(`${API}/datasets/upload`, {
        multipart: { file: { name, mimeType: "text/csv", buffer } },
      });
      expect(res.status(), `${name} must not cause a 500`).not.toBe(500);
      if (res.status() === 200) {
        await request.delete(`${API}/datasets/${(await res.json()).dataset_id}`);
      }
    }
  });
});
