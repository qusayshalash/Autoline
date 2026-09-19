import { expect, test, type Page } from "@playwright/test";
import { ADMIN, API, requireCredentials, signIn } from "./helpers";

test.beforeAll(() => requireCredentials(ADMIN, "admin"));

/**
 * Setting a record key, correcting a cell, and adding a later batch - through the
 * interface, with the keyboard, the way a person does it.
 *
 * The assertion that matters is the last one. `raw_data` is rebuilt from the original
 * upload on every import, so a correction and an appended batch that live only in the
 * table would both be gone afterwards, silently. They are kept outside it precisely so
 * they can be put back, and only a real re-import proves that they are.
 */

const BASE_ROWS = 12;
const WRONG_PLATE = "00060003";

/**
 * A name of its own per run.
 *
 * A run that fails part-way never reaches its own delete, so the next one found three
 * datasets by the same name and could not say which row it meant - a failure in the
 * *previous* run showing up as a confusing failure in this one. The sweep below removes
 * whatever earlier runs left; the unique name means a concurrent leftover cannot
 * confuse this one either.
 */
const FILENAME = `QA_TEST_records_${Date.now()}.csv`;

function baseCsv(): Buffer {
  const lines = ["plate,make,year,city"];
  for (let i = 0; i < BASE_ROWS; i++) {
    const year = i === 3 ? "غير معروف" : String(2000 + i);
    lines.push(`${String(60000 + i).padStart(8, "0")},${["تويوتا", "كيا"][i % 2]},${year},رام الله`);
  }
  return Buffer.from(lines.join("\n") + "\n", "utf-8");
}

/** A batch restating one record that is already here, and adding one that is not. */
const BATCH = Buffer.from(
  "plate,make,year,city\n" +
    "00060000,مرسيدس,2025,نابلس\n" +
    "00099001,هوندا,2023,غزة\n",
  "utf-8"
);

async function importDataset(request: Page["request"]): Promise<string> {
  const upload = await request.post(`${API}/datasets/upload`, {
    multipart: { file: { name: FILENAME, mimeType: "text/csv", buffer: baseCsv() } },
  });
  expect(upload.status(), "upload should succeed").toBe(200);
  const id: string = (await upload.json()).dataset_id;

  const started = await request.post(`${API}/datasets/${id}/import`, {
    data: { encoding: "utf-8", delimiter: ",", has_header: true },
  });
  const job = await started.json();
  await expect
    .poll(async () => (await (await request.get(`${API}/jobs/${job.id}`)).json()).status, {
      timeout: 60_000,
    })
    .toBe("done");
  return id;
}

/** The value in one column of one record, read back from the server. */
async function valueOf(request: Page["request"], id: string, plate: string, column: string) {
  const res = await request.post(`${API}/datasets/${id}/data`, {
    data: { source: "raw", filters: [{ column: "plate", op: "eq", value: plate }] },
  });
  const body = await res.json();
  if (!body.rows.length) return null;
  return body.rows[0][body.columns.indexOf(column)];
}

test.describe("Records", () => {
  test("set a key, correct a cell, add a batch - and re-import without losing either", async ({
    page,
    request,
  }) => {
    await signIn(page, ADMIN);
    await request.post(`${API}/auth/login`, {
      data: { username: ADMIN.user, password: ADMIN.pass },
    });
    // whatever an interrupted earlier run left behind
    for (const d of await (await request.get(`${API}/datasets`)).json()) {
      if (String(d.original_filename).startsWith("QA_TEST_records")) {
        await request.delete(`${API}/datasets/${d.id}`);
      }
    }
    const id = await importDataset(request);

    // ---- the cells are read-only until something identifies a record ----------------
    await page.goto(`/datasets/${id}/explore`);
    await expect(page.getByRole("table")).toBeVisible();
    expect(
      await page.locator("button.cell-edit").count(),
      "nothing identifies a record yet, so nothing is editable"
    ).toBe(0);

    // ---- choosing the key, and being told what it would mean ------------------------
    await page.getByRole("button", { name: "حدّد المعرّف" }).click();
    const dialog = page.getByRole("dialog", { name: "معرّف السجلّ" });
    await expect(dialog).toBeVisible();

    // "make" repeats, and the count is what says so rather than a bare refusal
    await dialog.getByRole("button", { name: /^plate$/ }).click();
    await page.getByRole("option", { name: "make" }).click();
    await expect(dialog.locator(".key-verdict-bad")).toContainText(/\d+/);
    await expect(dialog.getByRole("button", { name: "اعتمد" })).toBeDisabled();

    await dialog.getByRole("button", { name: /^make$/ }).click();
    await page.getByRole("option", { name: "plate" }).click();
    await expect(dialog.locator(".key-verdict-good")).toBeVisible();
    await dialog.getByRole("button", { name: "اعتمد" }).click();
    await expect(dialog).toHaveCount(0);

    // ---- correcting a cell, with the keyboard --------------------------------------
    const cell = page
      .getByRole("button", { name: "صحّح year" })
      .filter({ hasText: "غير معروف" });
    await expect(cell).toHaveCount(1);
    await cell.click();

    const editor = page.locator("input.cell-editor");
    await expect(editor).toBeFocused();
    await editor.fill("2003");
    await editor.press("Enter");

    await expect(page.locator(".cell-corrected").filter({ hasText: "2003" })).toBeVisible();
    expect(await valueOf(request, id, WRONG_PLATE, "year")).toBe("2003");

    // the cell says what the file itself had, which is the point of keeping it
    await expect(
      page.locator(".cell-corrected").filter({ hasText: "2003" })
    ).toHaveAttribute("title", /غير معروف/);

    // ---- a key column is not correctable -------------------------------------------
    expect(
      await page.getByRole("button", { name: "صحّح plate" }).count(),
      "the column that says which record this is cannot be edited"
    ).toBe(0);

    // ---- adding a later batch -------------------------------------------------------
    await page.goto("/");
    const row = page.locator(".dataset-row").filter({ hasText: FILENAME });
    await row.getByRole("button", { name: "إضافة دفعة" }).click();

    const appendDialog = page.getByRole("dialog", { name: "إضافة دفعة جديدة" });
    await expect(appendDialog).toBeVisible();
    await expect(appendDialog, "it should say it will replace, not just add").toContainText(
      "سيُستبدل"
    );
    await appendDialog
      .locator('input[type=file]')
      .setInputFiles({ name: "QA_TEST_batch.csv", mimeType: "text/csv", buffer: BATCH });

    await expect(appendDialog.locator(".append-result")).toBeVisible({ timeout: 20_000 });
    // two rows arrived; one of them stood in for a record already here, so the total
    // rises by one, not by two
    await expect(appendDialog.locator(".append-result")).toContainText("سجلّ واحد");
    const after = await (await request.get(`${API}/datasets/${id}`)).json();
    expect(after.row_count_raw).toBe(BASE_ROWS + 1);

    expect(await valueOf(request, id, "00060000", "year")).toBe("2025");
    expect(await valueOf(request, id, "00099001", "make")).toBe("هوندا");

    // ---- what the batch brought, marked in the grid ------------------------------------
    await page.goto(`/datasets/${id}/explore`);
    await expect(page.getByRole("table")).toBeVisible();

    // the filter is the answer to "show me the delivery" - scanning for a colour is not
    const recent = page.getByRole("button", { name: /الوارد حديثًا/ });
    await expect(recent).toBeVisible();
    await recent.click();

    await expect(page.locator(".arrival-mark.new")).toHaveCount(1);
    await expect(page.locator(".arrival-mark.updated")).toHaveCount(1);
    await expect(page.locator(".sheet-grid tbody tr")).toHaveCount(2);

    // colour is not the only channel: each mark carries a sentence a reader can hear
    await expect(page.locator(".arrival-mark.new")).toHaveAttribute("title", /جديد/);
    await expect(page.locator(".arrival-mark.updated")).toHaveAttribute("title", /حُدِّث/);

    await page.getByRole("button", { name: /أظهر الكل/ }).click();
    await expect(page.locator(".sheet-grid tbody tr")).toHaveCount(BASE_ROWS + 1);

    // ---- the one that matters --------------------------------------------------------
    const reimport = await request.post(`${API}/datasets/${id}/import`, {
      data: { encoding: "utf-8", delimiter: ",", has_header: true },
    });
    await expect
      .poll(
        async () =>
          (await (await request.get(`${API}/jobs/${(await reimport.json()).id}`)).json()).status,
        { timeout: 60_000 }
      )
      .toBe("done");

    expect(
      await valueOf(request, id, WRONG_PLATE, "year"),
      "the correction must survive the table being rebuilt from the file"
    ).toBe("2003");
    expect(
      await valueOf(request, id, "00099001", "make"),
      "and so must the appended record"
    ).toBe("هوندا");
    expect(
      await valueOf(request, id, "00060000", "year"),
      "and the batch's replacement of an existing record"
    ).toBe("2025");

    const final = await (await request.get(`${API}/datasets/${id}`)).json();
    expect(final.row_count_raw).toBe(BASE_ROWS + 1);

    // replaying a batch is not arriving: a re-import must not look like a fresh delivery
    const arrivals = await (await request.get(`${API}/datasets/${id}/arrivals`)).json();
    expect(arrivals.new).toBe(1);
    expect(arrivals.updated).toBe(1);

    // ---- putting the file's own value back -------------------------------------------
    await page.goto(`/datasets/${id}/explore`);
    const corrected = page.locator(".cell-corrected").filter({ hasText: "2003" });
    await expect(corrected).toBeVisible();
    await page
      .getByRole("button", { name: "أعد year إلى ما في الملف" })
      .click();
    await expect(page.locator(".cell-corrected")).toHaveCount(0);
    expect(await valueOf(request, id, WRONG_PLATE, "year")).toBe("غير معروف");

    await request.delete(`${API}/datasets/${id}`);
  });
});
