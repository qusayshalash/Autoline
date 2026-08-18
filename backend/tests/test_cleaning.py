"""Cleaning, and the size figure it reports.

Cleaning is destructive by design, so what matters is that it removes exactly what it
says it removed and nothing else. Each test therefore checks the *reported* counts
against the file and the resulting table against both.

The byte-size test is the important one in this file: the reported cleaned size used to
come from writing the whole table out to a throwaway CSV - 739 MB per run on the real
file - and now comes from arithmetic. Arithmetic that is only trustworthy if it agrees
with an actual export to the byte, which is what is checked here.
"""

import csv

import pytest
import synthetic
from app.db.connection import datasets
from app.services import cleaning
from helpers import rows_as_dicts, total


@pytest.fixture
def fresh(admin, csv_path):
    """A private copy of the dataset. Cleaning replaces the cleaned table, so tests that
    clean cannot share the session-wide dataset with tests that read it."""
    from conftest import wait_for_job

    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("clean.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    ds = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{ds}/import",
        json={"encoding": synthetic.ENCODING, "delimiter": synthetic.DELIMITER,
              "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    return ds


def clean(client, dataset_id, **config) -> dict:
    r = client.post(f"/api/datasets/{dataset_id}/clean", json=config)
    assert r.status_code == 200, r.text
    return r.json()


def test_cleaning_nothing_changes_nothing(admin, fresh, oracle):
    result = clean(admin, fresh)
    assert result["rows_before"] == result["rows_after"] == len(oracle)
    assert result["duplicates_removed"] == 0
    assert result["filtered_out"] == 0
    assert result["columns_dropped"] == []


def test_dedupe_removes_exactly_the_duplicate_rows(admin, fresh, oracle):
    """The fixture holds one byte-identical pair. Full-row distinct must remove one row -
    not the pair, and not rows that merely share a column.
    """
    result = clean(admin, fresh, dedupe=True)
    assert result["duplicates_removed"] == 1
    assert result["rows_after"] == len(oracle) - 1
    assert total(admin, fresh, source="cleaned") == len(oracle) - 1


def test_dedupe_on_a_key_column_keeps_one_row_per_value(admin, fresh, oracle):
    result = clean(admin, fresh, dedupe=True, dedupe_key_columns=["baalut"])
    distinct_owners = len({r["baalut"] for r in oracle})
    assert result["rows_after"] == distinct_owners
    assert result["duplicates_removed"] == len(oracle) - distinct_owners


def test_dropping_columns_removes_them_and_reports_them(admin, fresh, oracle):
    keep = ["mispar_rechev", "tozeret_nm", "sug_delek_nm"]
    result = clean(admin, fresh, keep_columns=keep)
    assert sorted(result["columns_dropped"]) == sorted(set(synthetic.COLUMNS) - set(keep))
    assert result["rows_after"] == len(oracle), "dropping columns must not drop rows"

    rows = rows_as_dicts(admin, fresh, source="cleaned")
    assert list(rows[0].keys()) == keep


def test_a_filter_keeps_the_matching_rows_and_reports_the_rest(admin, fresh, oracle):
    result = clean(
        admin, fresh,
        filters=[{"column": "sug_delek_nm", "op": "eq", "value": "בנזין"}],
    )
    expected = sum(1 for r in oracle if r["sug_delek_nm"] == "בנזין")
    assert result["rows_after"] == expected
    assert result["filtered_out"] == len(oracle) - expected
    assert total(admin, fresh, source="cleaned") == expected


def test_the_reported_numbers_always_reconcile(admin, fresh, oracle):
    """before - duplicates - filtered = after. If this ever fails, the report is telling
    the user something other than what happened to their data.
    """
    result = clean(
        admin, fresh,
        dedupe=True,
        filters=[{"column": "baalut", "op": "not_null"}],
    )
    assert (
        result["rows_before"] - result["duplicates_removed"] - result["filtered_out"]
        == result["rows_after"]
    )
    assert result["rows_after"] == total(admin, fresh, source="cleaned")


def test_cleaning_leaves_the_raw_table_untouched(admin, fresh, oracle):
    """The raw table is the record of what was imported. Cleaning writes a second table;
    it must never be able to destroy the first.
    """
    clean(admin, fresh, dedupe=True,
          filters=[{"column": "sug_delek_nm", "op": "eq", "value": "בנזין"}])
    assert total(admin, fresh, source="raw") == len(oracle)


def test_cleaning_is_repeatable_from_the_raw_table(admin, fresh, oracle):
    """Each run starts from raw, not from the previous result - otherwise two runs of the
    same filter would narrow the data twice and the config would not describe the output.
    """
    first = clean(admin, fresh, filters=[{"column": "sug_delek_nm", "op": "eq", "value": "בנזין"}])
    second = clean(admin, fresh, filters=[{"column": "sug_delek_nm", "op": "eq", "value": "בנזין"}])
    assert first["rows_after"] == second["rows_after"]

    widened = clean(admin, fresh)
    assert widened["rows_after"] == len(oracle)


def test_an_unknown_keep_column_is_a_400(admin, fresh):
    r = admin.post(f"/api/datasets/{fresh}/clean", json={"keep_columns": ["no_such"]})
    assert r.status_code == 400, r.text


def test_the_history_records_each_run(admin, fresh):
    clean(admin, fresh, dedupe=True)
    r = admin.get(f"/api/datasets/{fresh}/cleaning-operations")
    assert r.status_code == 200, r.text
    assert len(r.json()) >= 1


# ---- the computed CSV size ---------------------------------------------------------


def test_computed_csv_size_matches_a_real_export_to_the_byte(admin, fresh, tmp_path):
    """The claim being tested: the size can be calculated instead of written.

    Everything awkward about CSV width is present in the fixture on purpose - a field
    with a comma, a field with a double quote, a field with a newline, Hebrew text where
    one character is two bytes, and NULLs. Any of those handled wrongly shows up here as
    a mismatch, and the arithmetic is only worth trusting if the match is exact.
    """
    clean(admin, fresh)  # produce cleaned_data

    cur = datasets.cursor(fresh)
    columns = [r[0] for r in cur.execute("DESCRIBE cleaned_data").fetchall()]
    computed = cleaning.csv_byte_size(cur, "cleaned_data", columns)

    out = tmp_path / "actual.csv"
    escaped = str(out).replace("'", "''")
    cur.execute(f"COPY cleaned_data TO '{escaped}' (FORMAT CSV, HEADER)")
    actual = out.stat().st_size

    assert computed == actual, f"computed {computed:,} vs written {actual:,}"


def test_the_size_counts_bytes_not_characters(admin, fresh):
    """The bug this guards against cost 13% on the real file: DuckDB's length() counts
    characters, and Hebrew is two bytes per character in UTF-8. The check is that the
    reported size exceeds the character count of the same content - which it can only do
    if bytes are being counted.
    """
    clean(admin, fresh)
    cur = datasets.cursor(fresh)
    columns = [r[0] for r in cur.execute("DESCRIBE cleaned_data").fetchall()]
    computed = cleaning.csv_byte_size(cur, "cleaned_data", columns)

    body = " + ".join(f'length(coalesce("{c}", \'\'))' for c in columns)
    chars = cur.execute(f"SELECT SUM({body}) FROM cleaned_data").fetchone()[0]
    assert computed > chars


def test_the_size_of_an_empty_table_is_just_the_header(admin, fresh):
    result = clean(
        admin, fresh, filters=[{"column": "sug_delek_nm", "op": "eq", "value": "no-such-fuel"}]
    )
    assert result["rows_after"] == 0

    cur = datasets.cursor(fresh)
    columns = [r[0] for r in cur.execute("DESCRIBE cleaned_data").fetchall()]
    computed = cleaning.csv_byte_size(cur, "cleaned_data", columns)
    assert computed == len(",".join(columns).encode("utf-8")) + 1


def test_no_column_means_no_bytes(admin, fresh):
    cur = datasets.cursor(fresh)
    assert cleaning.csv_byte_size(cur, "raw_data", []) == 0


def test_the_reported_reduction_is_consistent_with_the_sizes(admin, fresh):
    result = clean(admin, fresh, keep_columns=["mispar_rechev", "sug_delek_nm"])
    assert result["cleaned_file_bytes"] < result["raw_file_bytes"]
    assert 0 < result["reduction_pct"] < 100
