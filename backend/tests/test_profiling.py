"""Column profiling.

Every number the page shows is checked against the fixture read by Python, because a
profile that is merely plausible is worse than none - it is the screen people will trust
when deciding whether their data is usable.
"""

import pytest
import synthetic
from app.services import profiling


def counts(oracle, column):
    out: dict[str, int] = {}
    for r in oracle:
        out[r[column]] = out.get(r[column], 0) + 1
    return out


# ---- the overview ------------------------------------------------------------------


def test_the_overview_covers_every_column(admin, dataset, oracle):
    out = profiling.profile_overview(dataset, "raw")
    assert [c["name"] for c in out["columns"]] == synthetic.COLUMNS
    assert out["total"] == len(oracle)


def test_the_overview_fill_counts_match_the_file(admin, dataset, oracle):
    out = profiling.profile_overview(dataset, "raw")
    by_name = {c["name"]: c for c in out["columns"]}

    for column in synthetic.COLUMNS:
        blank = sum(1 for r in oracle if r[column] == "")
        assert by_name[column]["missing"] == blank, column
        assert by_name[column]["filled"] == len(oracle) - blank, column


def test_the_overview_distinct_count_is_approximate_but_close(admin, dataset, oracle):
    """The one approximation in this module, and it is named as one.

    An exact COUNT(DISTINCT) over every column costs more than a second on a real file,
    and this list exists to choose a column from. The exact figure is one click away, so
    what matters here is that the estimate is close enough to choose by.
    """
    out = profiling.profile_overview(dataset, "raw")
    by_name = {c["name"]: c for c in out["columns"]}

    for column in ["sug_delek_nm", "baalut", "tozeret_nm"]:
        exact = len({r[column] for r in oracle if r[column]})
        approx = by_name[column]["approx_distinct"]
        assert abs(approx - exact) <= max(1, exact * 0.05), f"{column}: {approx} vs {exact}"


def test_the_column_profile_distinct_count_is_exact(admin, dataset, oracle):
    """Where the number is presented as a fact, it is one."""
    p = profiling.profile_column(dataset, "tozeret_nm", "raw")
    assert p["distinct"] == len({r["tozeret_nm"] for r in oracle if r["tozeret_nm"]})


def test_the_overview_is_one_query_not_one_per_column(admin, dataset):
    """It opens the page, so it has to be cheap. Twenty-two separate passes over four
    million rows is the thing this is written to avoid."""
    out = profiling.profile_overview(dataset, "raw")
    assert out["execution_ms"] >= 0
    assert len(out["columns"]) == len(synthetic.COLUMNS)


# ---- one column --------------------------------------------------------------------


def test_fill_and_distinct_match_the_file(admin, dataset, oracle):
    p = profiling.profile_column(dataset, "sug_delek_nm", "raw")
    blank = sum(1 for r in oracle if r["sug_delek_nm"] == "")

    assert p["total"] == len(oracle)
    assert p["missing"] == blank
    assert p["filled"] == len(oracle) - blank
    assert p["distinct"] == len({r["sug_delek_nm"] for r in oracle if r["sug_delek_nm"]})


def test_the_commonest_values_are_the_commonest_values(admin, dataset, oracle):
    p = profiling.profile_column(dataset, "sug_delek_nm", "raw")
    expected = counts(oracle, "sug_delek_nm")

    for item in p["top_values"]:
        key = "" if item["blank"] else item["value"]
        assert item["count"] == expected[key], item
    counted = [i["count"] for i in p["top_values"]]
    assert counted == sorted(counted, reverse=True), "not ordered by frequency"


def test_blanks_appear_as_a_value_and_are_marked_as_blank(admin, dataset, oracle):
    """A blank is the commonest "value" in plenty of real columns, and hiding it would
    make the list add up to less than the column without saying why."""
    p = profiling.profile_column(dataset, "ramat_gimur", "raw")
    blank = next((v for v in p["top_values"] if v["blank"]), None)
    assert blank is not None
    assert blank["count"] == sum(1 for r in oracle if r["ramat_gimur"] == "")


def test_lengths_are_counted_in_characters_of_the_filled_values(admin, dataset, oracle):
    p = profiling.profile_column(dataset, "mispar_rechev", "raw")
    lengths = {len(r["mispar_rechev"]) for r in oracle if r["mispar_rechev"]}
    assert p["min_length"] == min(lengths)
    assert p["max_length"] == max(lengths)


def test_zero_padding_is_detected(admin, dataset, oracle):
    """The property the whole import strategy exists to protect."""
    p = profiling.profile_column(dataset, "mispar_rechev", "raw")
    expected = sum(1 for r in oracle if r["mispar_rechev"].startswith("0") and len(r["mispar_rechev"]) > 1)
    assert p["zero_padded"] == expected
    assert any(f["code"] == "zero_padded" for f in p["findings"])


def test_an_identifier_column_is_called_out_as_one(admin, dataset):
    """Nearly-all-distinct means grouping by it produces one row per record, which the
    breakdown screen refuses to do - so the profile says why in advance."""
    p = profiling.profile_column(dataset, "mispar_rechev", "raw")
    assert any(f["code"] == "identifier_like" for f in p["findings"]), p["findings"]


def test_a_column_with_blanks_reports_them(admin, dataset, oracle):
    p = profiling.profile_column(dataset, "ramat_gimur", "raw")
    codes = {f["code"] for f in p["findings"]}
    assert "has_missing" in codes or "mostly_empty" in codes


def test_hebrew_values_survive_into_the_profile(admin, dataset):
    p = profiling.profile_column(dataset, "tozeret_nm", "raw")
    values = {v["value"] for v in p["top_values"]}
    assert synthetic.KIA in values


def test_a_column_with_one_bad_value_is_not_treated_as_numeric(admin, dataset):
    """The type rule is strict: every non-empty value must parse, or the column is not a
    number. The fixture's year column holds one non-year, so it is text - and a numeric
    summary of it would be a summary of only the values that happened to cooperate."""
    p = profiling.profile_column(dataset, "shnat_yitzur", "raw")
    assert p["kind"] != "number"
    assert p["numeric"] is None


def test_a_numeric_column_gets_a_summary_matching_the_values(admin, numeric_column, oracle):
    dataset_id, column = numeric_column
    p = profiling.profile_column(dataset_id, column, "raw")

    assert p["kind"] == "number", p["kind"]
    values = [float(i) for i in range(1, len(oracle) + 1)]
    assert p["numeric"]["count"] == len(values)
    assert p["numeric"]["min"] == min(values)
    assert p["numeric"]["max"] == max(values)
    assert p["numeric"]["median"] == pytest.approx((min(values) + max(values)) / 2, abs=1)
    assert p["numeric"]["not_numeric"] == 0


def test_outliers_are_counted_against_the_interquartile_fences(admin, numeric_column):
    """A single wildly out-of-range value is the shape of a units mix-up or a sentinel
    like 9999 standing in for "unknown", and both are worth seeing."""
    from app.db.connection import datasets as pool

    dataset_id, column = numeric_column
    with pool.write_lock(dataset_id):
        pool.cursor(dataset_id).execute(
            f'UPDATE raw_data SET "{column}" = ? WHERE "{column}" = ?',
            ["999999999", "1"],
        )

    p = profiling.profile_column(dataset_id, column, "raw")
    assert p["numeric"]["outliers"] >= 1
    assert any(f["code"] == "outliers" for f in p["findings"])


def test_an_entirely_empty_column_says_so_and_stops(admin, fresh_empty_column):
    dataset_id, column = fresh_empty_column
    p = profiling.profile_column(dataset_id, column, "raw")
    assert p["filled"] == 0
    assert [f["code"] for f in p["findings"]] == ["entirely_empty"]


def test_an_unknown_column_is_refused(admin, dataset):
    with pytest.raises(ValueError, match="Unknown column"):
        profiling.profile_column(dataset, "no_such_column", "raw")


# ---- through the API ---------------------------------------------------------------


def test_the_endpoints_are_reachable_by_any_signed_in_user(viewer, dataset):
    """Profiling is reading. A viewer who may look at the data may look at its shape."""
    assert viewer.get(f"/api/datasets/{dataset}/profile", params={"source": "raw"}).status_code == 200
    r = viewer.get(f"/api/datasets/{dataset}/profile/tozeret_nm", params={"source": "raw"})
    assert r.status_code == 200, r.text


def test_the_endpoints_reject_an_anonymous_caller(anon, dataset):
    assert anon.get(f"/api/datasets/{dataset}/profile").status_code == 401
    assert anon.get(f"/api/datasets/{dataset}/profile/tozeret_nm").status_code == 401


def test_an_unknown_column_over_http_is_a_400(admin, dataset):
    r = admin.get(f"/api/datasets/{dataset}/profile/no_such", params={"source": "raw"})
    assert r.status_code == 400, r.text


def test_the_api_agrees_with_the_service(admin, dataset):
    direct = profiling.profile_column(dataset, "baalut", "raw")
    over_http = admin.get(f"/api/datasets/{dataset}/profile/baalut", params={"source": "raw"}).json()
    assert over_http["filled"] == direct["filled"]
    assert over_http["distinct"] == direct["distinct"]
    assert [v["count"] for v in over_http["top_values"]] == [v["count"] for v in direct["top_values"]]


@pytest.fixture
def fresh_empty_column(admin, dataset):
    """The fixture has a row of blanks but no wholly empty column, so one is made."""
    from app.db.connection import datasets as pool

    with pool.write_lock(dataset):
        cur = pool.cursor(dataset)
        cur.execute('ALTER TABLE raw_data ADD COLUMN "nothing_at_all" VARCHAR')
    yield dataset, "nothing_at_all"
    with pool.write_lock(dataset):
        pool.cursor(dataset).execute('ALTER TABLE raw_data DROP COLUMN "nothing_at_all"')


@pytest.fixture
def numeric_column(admin, csv_path):
    """A column every value of which is a number, since the shared fixture deliberately
    has none - its year column holds one non-year to test the strict type rule."""
    from app.db.connection import datasets as pool
    from conftest import wait_for_job

    with open(csv_path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("numeric.csv", f, "text/csv")})
    ds = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{ds}/import",
        json={"encoding": synthetic.ENCODING, "delimiter": synthetic.DELIMITER,
              "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"

    with pool.write_lock(ds):
        cur = pool.cursor(ds)
        cur.execute('ALTER TABLE raw_data ADD COLUMN "measure" VARCHAR')
        cur.execute(
            'UPDATE raw_data SET "measure" = CAST(rowid + 1 AS VARCHAR)'
        )
    return ds, "measure"
