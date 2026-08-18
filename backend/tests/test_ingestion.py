"""What the import must preserve.

Every assertion here compares the imported table against the same file read by Python's
csv module. The import is only correct if the two agree exactly - a row count that is
close, or an identifier that is numerically equal, is a failure.
"""

import synthetic
from helpers import rows_as_dicts


def test_every_row_arrives(admin, dataset, oracle):
    imported = rows_as_dicts(admin, dataset, source="raw")
    assert len(imported) == len(oracle)


def test_the_header_becomes_the_columns_in_order(admin, dataset):
    r = admin.get(f"/api/datasets/{dataset}")
    assert r.json()["columns"] == synthetic.COLUMNS


def test_the_whole_table_is_identical_to_the_file(admin, dataset, oracle):
    """The strongest statement available: not counts, not samples - every cell of every
    row, in order.

    The one permitted difference is empty-versus-NULL, which the next test pins down on
    its own; everything else must match character for character."""
    imported = rows_as_dicts(admin, dataset, source="raw", sort_by="mispar_rechev")
    expected = sorted(oracle, key=lambda r: r["mispar_rechev"])
    got = sorted(imported, key=lambda r: r["mispar_rechev"])
    assert len(got) == len(expected)
    for g, e in zip(got, expected):
        for column in synthetic.COLUMNS:
            assert (g[column] or "") == (e[column] or ""), f"{column} of row {e['mispar_rechev']}"


def test_an_empty_field_becomes_null(admin, dataset, oracle):
    """DuckDB reads an unquoted empty field as NULL, so a blank in the file is a NULL in
    the table. This is why every missing-value check in the app tests for NULL *or* '':
    the same absent value can be either, depending on whether it was quoted.

    Locked down here because the day it changes, "unspecified" counts change with it.
    """
    blanks_in_file = sum(1 for r in oracle if r["sug_delek_nm"] == "")
    assert blanks_in_file > 0, "the fixture is supposed to contain blanks"

    imported = rows_as_dicts(admin, dataset, source="raw")
    assert sum(1 for r in imported if r["sug_delek_nm"] is None) == blanks_in_file
    assert sum(1 for r in imported if r["sug_delek_nm"] == "") == 0


def test_leading_zeros_survive(admin, dataset):
    """The whole reason the loader forces all_varchar. Inferred as a number this becomes
    42 and the identifier is destroyed - silently, and unrecoverably."""
    rows = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009042"}],
    )
    assert len(rows) == 1
    assert rows[0]["mispar_rechev"] == "00009042"


def test_hebrew_text_is_not_mojibake(admin, dataset):
    """cp1255 read as cp1252 produces plausible-looking Latin garbage rather than an
    error, so this needs an equality check against the real string."""
    rows = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009042"}],
    )
    assert rows[0]["tozeret_nm"] == synthetic.KIA
    assert rows[0]["sug_delek_nm"] == "בנזין"


def test_a_field_containing_the_delimiter_stays_one_field(admin, dataset):
    rows = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009043"}],
    )
    assert rows[0]["tzeva_rechev"] == "שחור, מטאלי"
    assert rows[0]["ramat_gimur"] == "EX"  # nothing shifted along


def test_a_field_containing_a_double_quote_survives_requoting(admin, dataset):
    """The value passes through two serializers - the normalizer and DuckDB's reader - so
    a mishandled `""` shows up as a lost or doubled quote."""
    rows = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009044"}],
    )
    assert rows[0]["tzeva_rechev"] == 'גלגלי 15" אלומיניום'


def test_a_field_containing_a_newline_stays_one_row(admin, dataset):
    """One record spanning two physical lines. Counted per line instead of per record,
    this inflates the row count and shifts every field after it."""
    rows = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009045"}],
    )
    assert len(rows) == 1
    assert rows[0]["tzeva_rechev"] == "כסף\nבהיר"
    assert rows[0]["ramat_gimur"] == "L"


def test_blank_fields_stay_blank_and_the_row_is_kept(admin, dataset):
    """A row of blanks is still a row. Dropping it would quietly change every total."""
    rows = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009048"}],
    )
    assert len(rows) == 1
    assert all(rows[0][c] in ("", None) for c in synthetic.COLUMNS if c != "mispar_rechev")


def test_the_duplicate_pair_is_imported_twice(admin, dataset):
    """Import must not deduplicate. Removing duplicates is cleaning's decision, made
    explicitly and reported."""
    rows = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009049"}],
    )
    assert len(rows) == 2
    assert rows[0] == rows[1]


def test_encoding_detection_finds_a_hebrew_codepage(admin, csv_path, tmp_path):
    """Detection is advisory - the wizard lets the user override it - so this checks the
    guess is a Hebrew-capable codepage, not one exact label."""
    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("detect.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["detected_delimiter"] == "|"
    guessed = body["detected_encoding"].lower().replace("-", "").replace("_", "")
    assert guessed in {"cp1255", "windows1255", "hebrew", "iso88598", "iso88598i"}, guessed


def test_a_wrong_stated_encoding_is_reported_rather_than_silently_wrong(admin, csv_path):
    """Importing cp1255 bytes as utf-8 cannot be silently correct. It either fails or
    substitutes replacement characters - what must not happen is a "ready" dataset whose
    Hebrew is quietly destroyed with no trace."""
    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("wrong.csv", f, "text/csv")})
    ds = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{ds}/import",
        json={"encoding": "utf-8", "delimiter": "|", "has_header": True},
    )
    from conftest import wait_for_job

    job = wait_for_job(admin, r.json()["id"])
    if job["status"] == "error":
        return  # refused outright, which is the other acceptable outcome
    rows = rows_as_dicts(
        admin, ds, source="raw",
        filters=[{"column": "mispar_rechev", "op": "eq", "value": "00009042"}],
    )
    assert rows[0]["tozeret_nm"] != synthetic.KIA
    assert "\ufffd" in rows[0]["tozeret_nm"], "damage must be visible, not silent"
