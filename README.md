# Autoline

[![CI](https://github.com/qusayshalash/Autoline/actions/workflows/ci.yml/badge.svg)](https://github.com/qusayshalash/Autoline/actions/workflows/ci.yml)

A web application for exploring, cleaning and analysing CSV files that are too large for
a spreadsheet. It was built against, and is measured against, a real one: the Israeli
vehicle registry — **4,114,487 rows, 867 MB, Windows-1255 Hebrew, pipe-delimited**.

Every figure in this README came from that file.

---

## What it does

**Explore.** A spreadsheet-style grid over the whole file. Filter, search, sort, group
and page through four million rows; a page comes back in tens of milliseconds because
only the page crosses the wire.

**Analyse.** Breakdowns of any column, and cross-tabs of any two — as counts, or as
percentages of the row, the column or the whole file. Charts and tables export to CSV,
XLSX and PDF, with Hebrew and Arabic shaped correctly in the PDF.

**Clean.** Drop columns, de-duplicate on any key, filter rows out. Every run reports
exactly what it removed and reconciles: `before − duplicates − filtered = after`.

**Judge the import.** A quality report on every file: what was blank, what failed to
parse, what looks inconsistent — so a bad file is visible before conclusions are drawn
from it.

**Administer.** Users, roles and per-permission access control, an activity log, storage
accounting with a preview-before-delete cleanup, verified backups, and login rate
limiting. Interface in Arabic, Hebrew and English, right-to-left and left-to-right, light
and dark.

---

## Running it

Requires Python 3.14 and Node 22+.

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt
cp .env.example .env            # then edit DATA_DIR - see the warning inside
python -m uvicorn app.main:app --port 8000 --reload
```

```bash
# frontend, in a second terminal
cd frontend
npm install
npm run dev
```

The app is then at `http://localhost:5173`. On first start the server creates an
administrator account and prints its credentials to the log — **change that password
immediately**.

```bash
# the test suite
cd backend
pytest -m "not real"            # 227 tests, ~30s, no data needed
```

---

## How it is built

| | |
|---|---|
| Backend | FastAPI, DuckDB 1.5, Pydantic v2, PyJWT |
| Frontend | React 19, TypeScript, Vite, TanStack Query, ECharts, react-i18next |
| Storage | One DuckDB file per dataset, plus a small catalogue database |
| Tests | 227 (+7 characterization tests against the real dataset) |

A dataset lives in its own DuckDB file, so listing files never opens a four-million-row
database and deleting one is a file deletion. A separate catalogue tracks metadata, jobs,
users, roles and the activity log. Long operations — import, cleaning, export, backup —
run as background jobs and are polled by id, because they outlast any sensible HTTP
timeout.

Nothing is estimated. Where a number is expensive to compute exactly, it is still
computed exactly, and where an approximation would be invisible it is refused on
principle: an analytics tool that is quietly a little bit wrong is worse than one that is
slow.

---

## Decisions worth explaining

These are the ones that were not obvious, and that each cost a real bug to learn.

### Every column is imported as text

The loader forces `all_varchar=true`. Type inference would read `00000042` as the number
42 and destroy several hundred thousand vehicle identifiers — silently, unrecoverably,
and in a way that still looks like plausible data afterwards. Dates and numbers are cast
at query time, where being wrong is visible and reversible.

### Byte length, not character length

The cleaning report shows how large the data would be as CSV. It used to produce that
figure by writing the whole table out to a temporary file — **739 MB per run**, deleted
immediately. It is now computed in SQL.

The first version of that computation used DuckDB's `length()`, which counts characters.
This file is Hebrew, where each character is two bytes in UTF-8, so it understated the
size by 13%. With `strlen()` the computation matches a real export to the byte:
`775,413,733` either way. A test asserts that equality on both synthetic and real data.

### Cross-tabs close by subtraction, never by sampling

A cross-tab shows the largest rows and columns and folds the rest into an "other" band.
That band is computed as `true total − sum of shown cells`, and the corner where both
axes are folded by inclusion–exclusion. Every row and column therefore sums to its real
total, even on a maximally sparse pairing — 10,091 models against 100 colours — where a
sampled remainder would be plausible and wrong.

### Prefix matching, because a marque hides inside a country

The manufacturer column pairs a marque with a country of assembly, and in Hebrew
**קיה** (Kia) is the last three letters of **טורקיה** (Turkey). A `contains` search for
Kia returns 45,462 rows too many — other marques assembled in Turkey. This is why
`starts_with` exists as a first-class filter, and why the audited figure of 426,259 Kia
vehicles is pinned in a test.

### Backups go through DuckDB, never through the filesystem

A live DuckDB file must never be copied byte for byte: the engine writes pages
continuously, and a copy taken mid-write captures a torn page. The database that comes
back opens fine and fails later. Backups are taken with `COPY FROM DATABASE`, which
produces a consistent snapshot while the server keeps running — and every one is then
reopened and its rows counted against the counts taken while writing. Nothing is called
verified until it has been read back.

### Where the data directory may not live

`DATA_DIR` must point somewhere no file-syncing client watches, for the same
torn-page reason. It must also not be under `AppData\Local` on Windows: that folder is
redirected per-application for packaged apps, so a tool running inside such a package
writes to its own private cache while the rest of the machine reads the real folder and
finds nothing. Both paths print identically in every error message. This project's data
spent a day inside an application cache before a file-id comparison revealed that two
supposedly different paths were the same file.

### Rate limiting that gives nothing away

Failed logins are counted against the username **as typed**, whether or not that account
exists, and an unknown username costs the same scrypt work as a real one. Otherwise the
status code and the response time between them would enumerate every account on the
system. Lockouts are always temporary and always liftable from the admin panel — a
permanent lock would let anyone who knows a username take that person's access away.

---

## Tests

```
227 passing, ~30 seconds, no external data required
```

The suite runs against a real stack — real DuckDB files, real HTTP routing, real auth
cookies — pointed at a throwaway data directory. Expected values come from reading the
fixture with Python's own `csv` module, so a filter that is merely plausible still fails.

The fixture is 489 rows and deliberately awkward: cp1255 Hebrew, zero-padded identifiers,
blank fields, a comma inside a value, a double quote inside a value, a newline inside a
value, LIKE wildcards as literal characters, a non-numeric year, and two byte-identical
rows for de-duplication to find.

A further seven tests, run with `pytest -m real`, lock in figures established by hand
against the original 867 MB file during a five-stage audit of the pipeline. They skip
themselves when that dataset is absent, so a fresh clone still runs green.

---

## Licence

Not yet chosen.
