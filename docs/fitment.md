# Filters that fit each vehicle (fitment)

> **بالعربي باختصار:** قسم «الفلاتر المناسبة» في بطاقة المركبة يقرأ من قاعدة بيانات
> مرجعية (`fitment.duckdb`، نحو 22 ميغا) **غير موجودة في GitHub عن قصد**، لأنها بيانات
> كتالوجات الشركات. تُبنى على جهاز قصي بأمر واحد (نحو 10 دقائق، مرة واحدة)، ثم **تُرفع
> إلى السيرفر يدويًا** عند النشر. بدونها لا يظهر القسم، ولا يحدث أي خطأ.

The vehicle card - in the catalog, on the record page and on the printed sheet - shows the
oil, air, fuel and cabin filters that four aftermarket catalogues fit to the vehicle, and
how far the catalogues agree. This document is for whoever works on it next: where the
data comes from, why it is not in the repository, how to build and deploy it, and what
was verified.

Code: `backend/app/services/fitment.py` (lookup), `backend/scripts/build_fitment.py`
(build), `frontend/src/components/FitmentPanel.tsx` (the section),
`backend/tests/test_fitment.py`.

---

## The data is not in the repository - on purpose

The reference database is **`<DATA_DIR>/reference/fitment.duckdb`**, about **22 MB**.

- It is catalogue data gathered from the filter makers' own sites (MANN-FILTER, UFI,
  JS Filter, Denckermann). The application may read it; the repository - which may be
  public - is not the place to republish it. So it lives in the data directory, beside
  the datasets, and **is never committed**.
- **Without the file the section simply does not appear.** `fitment.lookup()` returns
  `None`, the API sends `fitment: null`, and the card leaves the section out. No error,
  no broken page. A fresh checkout runs fine without it.
- Locally `DATA_DIR` is `C:\CSVStudioData`, so the file is
  `C:\CSVStudioData\reference\fitment.duckdb`. On the server the data directory is
  `/srv/autoline/data` (mounted as `/data` in the container), so the file goes to
  **`/srv/autoline/data/reference/fitment.duckdb`**.

## Building it (about 10 minutes, once)

```bash
cd backend
python scripts/build_fitment.py "<outputs dir>" "<Dataprime dir>"
```

On Qusay's machine:

- `<outputs dir>` = `C:\Users\ME\Documents\Codex\2026-08-21\new-chat\outputs`
- `<Dataprime dir>` = `C:\Users\ME\OneDrive\سطح المكتب\Dataprime`

It takes about **10 minutes** because it compares every pair of catalogues for all 79,580
vehicle configurations through their cross-references. It is run **once**, and again
only when the catalogue data itself is refreshed - not on every deployment, and not when
the registry changes (new vehicles find their configuration on their own; see below).
It writes to a temporary file and swaps it in at the end, so a failed build leaves the
previous database untouched.

What it reads:

| From | File | What it holds |
|---|---|---|
| outputs | `mann_ufi_jsfilter_denckermann_ufi_alternatives_configuration_fitment.csv` | for each of 79,580 configurations: every catalogue's parts and match status |
| outputs | `ufi_cross_references_full.csv` | UFI product -> OE numbers and other brands' codes |
| outputs | `mann_filter_oem_references.csv`, `mann_filter_vehicle_oem_references.csv` | MANN part -> OE numbers |
| Dataprime | `dataset.db` | JS Filter parts -> OE numbers |
| Dataprime | `denckermann.db` | Denckermann parts, found by OE number |
| Dataprime | `normalize.py` | the make parser the data was gathered with, reused as is |

## Deploying it to the server

The code deploys with `deploy/update.sh` as usual; the database has to be copied once,
separately. From PowerShell on the machine that built it:

```bash
scp "C:\CSVStudioData\reference\fitment.duckdb" root@<server>:/srv/autoline/data/reference/
```

Then on the server (create the folder first if it is not there, and give it to the app's
user):

```bash
mkdir -p /srv/autoline/data/reference
chown -R 1000:1000 /srv/autoline/data/reference
```

No restart is needed for a first copy - the file is opened on first use. **When
replacing an existing one, restart the backend** (`docker compose restart backend`):
the open database is cached for the life of the process.

---

## How a vehicle finds its filters

A vehicle is looked up by its **configuration key**: SHA-256 over seven of its registry
fields, joined with the unit separator `\x1f`:

```
tozeret_cd, sug_degem, degem_cd, degem_manoa, shnat_yitzur, sug_delek_nm, kvutzat_zihum
```

The recipe is the merged catalogue file's own. It was recovered from that file and then
**recomputed for all 4,114,487 registry vehicles - every one matched the file's key**.
Because the key comes from the vehicle's own record, a car registered after the
catalogues were gathered finds its configuration too, as long as that configuration was
already known. `tests/test_fitment.py` pins the key of a real vehicle (49-107-66, a 2009
Hyundai i30) so a change to the recipe cannot pass unnoticed.

There is no per-plate table and no fuzzy matching. In particular the lookup **never
matches on engine code alone**: `2ZR` is both a petrol Corolla and a hybrid Prius, with
different filters. A configuration the catalogues do not know shows "not available".

## How agreement is decided

Every source is kept separate - nothing is merged into one answer. For each filter type
the build decides one verdict and stores it:

- **agree** - two catalogues from different companies name parts that answer to the
  same original-equipment (car maker) number, *of the vehicle's own make*;
- **disagree** - both parts are referenced and share no such number: shown in red, to be
  settled before anything is ordered;
- **unlinked** - at least one part has no reference, so no comparison can be made
  (silence is not evidence either way);
- **single** - one catalogue only.

The method is Dataprime's `agreement.py`, **ported as it stands**, because its notes
record why simpler ones failed: a union-find over the cross-references chained 76% of all
codes into one group and made everything "agree"; comparing raw codes across catalogues
compared incompatible vocabularies and made everything "disagree". Links are kept to one
hop (two through a UFI product as pivot), and comparisons are restricted to the vehicle's
own make.

**The port was verified against Dataprime's published figures and reproduces all sixteen
of them exactly** (four filter types x four verdicts, counted in vehicles):

| type | agree | disagree | unlinked | single |
|---|---:|---:|---:|---:|
| oil | 900,812 | 20,080 | 233,807 | 2,170,337 |
| air | 823,603 | 61,740 | 251,716 | 2,008,370 |
| cabin | 873,825 | 73,810 | 294,352 | 2,150,513 |
| fuel | 75,278 | 3,740 | 83,789 | 980,146 |

MANN and JS Filter (and Denckermann) belong to different corporate groups, so their
agreement counts as independent confirmation. **UFI's cross-reference to MANN is not**: it
says a UFI part *is* the MANN part under another brand. The card lists those as "UFI
equivalents of the MANN part" - useful as stock alternatives, never as a second opinion.

## Coverage and what is still open

- **84%** of vehicles (3,461,376 of 4,114,487) have at least one catalogue's parts; oil
  and cabin filters are known for **87%** of non-electric vehicles, air 83%, fuel 76%.
- **226,273 fully electric vehicles** have no engine filters; the card says so.
- **`LIFETIME-FILTER`** is MANN's way of saying the fuel filter is sealed in the tank and
  never serviced - 2.24 million vehicles. It is shown in words, not as a part number, and
  is not counted as a part when agreement is decided.
- **211,857 vehicles are "ambiguous" at MANN** (several candidate types, none chosen) with
  no other catalogue covering them. They show "not available" for now; resolving them is
  the obvious next piece of work.
- The rule that governs all of it: **a wrong filter can damage an engine, so a missing
  part is reported as missing and never inferred from a similar car.**
