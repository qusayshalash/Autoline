# End-to-end suite

These tests sign in as real accounts and create, rename and delete real records. Point
them at a throwaway installation, never at one holding data you care about.

## Setting up a disposable instance

Run the backend against its own data directory, so nothing here touches your real
catalog:

```bash
DATA_DIR=C:/CSVStudioQA backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000
```

On first start with an empty directory the server prints a generated administrator
password once. Use that account, or create dedicated QA accounts from it.

## Running

The suite reads its credentials from the environment and never stores them:

```bash
QA_ADMIN_USER=admin QA_ADMIN_PASS=<generated> QA_VIEWER_USER=qa_viewer QA_VIEWER_PASS=<chosen> npx playwright test
```

`npx playwright test --ui` opens the interactive runner; `npx playwright show-report`
opens the HTML report after a run.

The viewer account needs the built-in **Viewer** role (only `datasets.view`) - the
permission tests assert it is refused everywhere else.

## What is covered

| File | Covers |
|---|---|
| `auth.spec.ts` | sign in, wrong password, empty form, HttpOnly cookie, deep-link redirect, sign out + back button, anonymous API refusal, tampered token |
| `permissions.spec.ts` | viewer sees no write controls, forbidden screen, the API refuses the viewer on 10 endpoints, no self-promotion, built-in roles protected |
| `dataset-lifecycle.spec.ts` | upload → import → read → rename → export (csv/xlsx/pdf) → delete, de-duplication, odd files |
| `data-grid.spec.ts` | pagination, page-size cap, search (Arabic/partial/case/wildcards), filters, numeric sort, injection probes, group-by totals, stored-XSS rendering |
| `admin.spec.ts` | user create/read/delete through the UI, duplicate conflict, every admin page loads clean, linkable settings sections, activity-log translations, trim floor |

## Test data

Everything the suite creates is prefixed `QA_TEST_`, and each test removes what it
made. If a run is interrupted, delete any leftover `QA_TEST_*` datasets and accounts
before the next one.

## Two tests are written to fail until a defect is fixed

- `data-grid.spec.ts › sorts a numeric column by value, not alphabetically`
- `admin.spec.ts › the activity log renders translated action names, not raw keys`

Both are deliberate regression guards, not flaky tests. They are described in the QA
report; when the underlying issues are fixed, these turn green and keep them fixed.
