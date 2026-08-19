"""The summary panel: how big the file was, how much cleaning took out of it.

Small module, but it is the first thing anyone reads about a dataset, and every figure
in it is copied from somewhere else - the catalog row, the newest cleaning run, the live
table. So the tests are mostly about *which* somewhere: whether "duplicates removed"
means the last run or the first, whether the column list follows a cleaning that dropped
one, whether the numbers still reconcile after the second run.

The dataset here is a private one per test. The session-wide fixture is cleaned by the
permission tests, so anything asserting "nothing has been cleaned yet" would pass or
fail depending on the order the files happened to run in.
"""

import pytest
import synthetic
from conftest import wait_for_job


@pytest.fixture
def fresh(admin, csv_path) -> str:
    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("stats.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    ds = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{ds}/import",
        json={
            "encoding": synthetic.ENCODING,
            "delimiter": synthetic.DELIMITER,
            "has_header": True,
        },
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    return ds


def summary(client, dataset_id: str) -> dict:
    r = client.get(f"/api/datasets/{dataset_id}/stats")
    assert r.status_code == 200, r.text
    return r.json()


def clean(client, dataset_id: str, **config) -> dict:
    r = client.post(f"/api/datasets/{dataset_id}/clean", json=config)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_summary_counts_the_rows_that_were_in_the_file(admin, fresh, oracle):
    assert summary(admin, fresh)["row_count_raw"] == len(oracle)


def test_the_raw_size_is_the_uploaded_file_byte_for_byte(admin, fresh, csv_path):
    assert summary(admin, fresh)["raw_file_bytes"] == csv_path.stat().st_size


def test_the_summary_lists_the_columns_in_file_order(admin, fresh):
    assert summary(admin, fresh)["columns"] == synthetic.COLUMNS


def test_before_any_cleaning_nothing_is_reported_as_removed(admin, fresh):
    """An imported-but-uncleaned dataset has no cleaned table, and the panel must say so
    rather than showing zeroes that read as "cleaning ran and found nothing"."""
    s = summary(admin, fresh)
    assert s["row_count_cleaned"] is None
    assert s["cleaned_file_bytes"] is None
    assert s["reduction_pct"] is None
    assert s["duplicates_removed"] == 0
    assert s["filtered_out"] == 0


def test_a_cleaning_run_shows_up_in_the_summary(admin, fresh, oracle):
    """The fixture holds exactly one byte-identical pair of rows."""
    clean(admin, fresh, dedupe=True)
    s = summary(admin, fresh)
    assert s["duplicates_removed"] == 1
    assert s["row_count_cleaned"] == len(oracle) - 1
    assert s["row_count_raw"] == len(oracle)  # the raw count is not touched by cleaning


def test_the_summary_describes_the_latest_run_and_not_the_first(admin, fresh, oracle):
    """Cleaning always restarts from the raw table, so a second run that does not dedupe
    puts the duplicate back. The panel has to follow it - reporting the first run for the
    rest of the dataset's life would describe a table that no longer exists.
    """
    clean(admin, fresh, dedupe=True)
    assert summary(admin, fresh)["duplicates_removed"] == 1

    clean(admin, fresh, dedupe=False)
    s = summary(admin, fresh)
    assert s["duplicates_removed"] == 0
    assert s["row_count_cleaned"] == len(oracle)


def test_dropping_a_column_shortens_the_column_list(admin, fresh):
    """The list describes the table as it now is, not as it arrived."""
    kept = [c for c in synthetic.COLUMNS if c != "ramat_gimur"]
    clean(admin, fresh, keep_columns=kept)
    assert summary(admin, fresh)["columns"] == kept


def test_a_filter_is_reported_as_rows_filtered_out(admin, fresh, oracle):
    clean(admin, fresh, filters=[{"column": "tozeret_nm", "op": "eq", "value": synthetic.KIA}])
    s = summary(admin, fresh)
    kia = sum(1 for r in oracle if r["tozeret_nm"] == synthetic.KIA)
    assert s["row_count_cleaned"] == kia
    assert s["filtered_out"] == len(oracle) - kia


def test_the_reduction_is_the_arithmetic_of_the_two_size_figures(admin, fresh):
    """Whatever the two sizes mean, the percentage must be derived from them and rounded
    to two places - a panel showing a reduction that does not follow from the sizes
    printed beside it is worse than one showing no reduction at all.
    """
    clean(admin, fresh, dedupe=True)
    s = summary(admin, fresh)
    raw, cleaned = s["raw_file_bytes"], s["cleaned_file_bytes"]
    assert s["reduction_pct"] == round((raw - cleaned) / raw * 100, 2)


def test_the_reduction_compares_two_differently_measured_sizes(admin, fresh):
    """Known hazard, pinned here so it cannot change unnoticed.

    raw_file_bytes is the uploaded file as it sits on disk - here cp1255 and pipe
    delimited, one byte per Hebrew character. cleaned_file_bytes is what the table
    *would* occupy as a UTF-8 comma-delimited CSV, where the same characters cost two.
    The two are not comparable, so on this fixture removing a duplicate row makes the
    "reduction" come out around -45%: the panel reports that cleaning grew the file.

    The figures themselves are each correct for what they measure; it is the subtraction
    between them that is not meaningful when the upload was not already UTF-8. Left as
    it is for now - changing it changes what the panel has always shown - but asserted
    so the day someone fixes it, this test is what tells them where the panel lives.
    """
    clean(admin, fresh, dedupe=True)
    s = summary(admin, fresh)
    assert s["row_count_cleaned"] < s["row_count_raw"]  # fewer rows ...
    assert s["cleaned_file_bytes"] > s["raw_file_bytes"]  # ... yet "bigger"
    assert s["reduction_pct"] < 0


def test_an_unknown_dataset_is_a_404(admin):
    r = admin.get("/api/datasets/no-such-dataset/stats")
    assert r.status_code == 404, r.text


def test_the_summary_needs_a_session(anon, fresh):
    assert anon.get(f"/api/datasets/{fresh}/stats").status_code == 401
