"""Breakdowns that report an aggregate over a second column instead of a row count.

Every expected figure here is worked out from the file by Python itself, the same way
the counting tests do it, so a wrong SQL aggregate cannot agree with a wrong expectation.

The year column in the fixture deliberately holds a value that is not a number, which is
what makes the parseability tests below real rather than hypothetical.
"""

import statistics

import pytest
from helpers import breakdown


def _numeric_by(oracle, group_column: str, measure_column: str) -> dict[str, list[float]]:
    """The measure values the file actually holds, per bucket, skipping the ones that are
    not numbers - which is the same set the SQL aggregate is allowed to see."""
    out: dict[str, list[float]] = {}
    for r in oracle:
        key = "__unspecified__" if r[group_column] == "" else r[group_column]
        try:
            value = float(r[measure_column])
        except ValueError:
            continue
        out.setdefault(key, []).append(value)
    return {k: v for k, v in out.items() if v}


def _measures(out: dict) -> dict[str, float]:
    return {
        ("__unspecified__" if i["unspecified"] else i["value"]): i["measure"]
        for i in out["items"]
    }


def test_the_average_matches_the_file(admin, dataset, oracle):
    out = breakdown(
        admin, dataset, group_by="tozeret_nm", source="raw", limit=50,
        measure_column="shnat_yitzur", agg="avg",
    )
    expected = {k: statistics.fmean(v) for k, v in _numeric_by(oracle, "tozeret_nm", "shnat_yitzur").items()}
    got = _measures(out)
    assert got.keys() == expected.keys()
    for key, value in expected.items():
        assert got[key] == pytest.approx(value)


@pytest.mark.parametrize(
    "agg,fn",
    [("sum", sum), ("min", min), ("max", max), ("median", statistics.median)],
)
def test_every_aggregate_matches_the_file(admin, dataset, oracle, agg, fn):
    out = breakdown(
        admin, dataset, group_by="baalut", source="raw", limit=50,
        measure_column="shnat_yitzur", agg=agg,
    )
    expected = {k: fn(v) for k, v in _numeric_by(oracle, "baalut", "shnat_yitzur").items()}
    got = _measures(out)
    assert got.keys() == expected.keys()
    for key, value in expected.items():
        assert got[key] == pytest.approx(value)


def test_the_count_is_the_rows_the_figure_rests_on(admin, dataset, oracle):
    """Not the rows in the bucket. A bucket holding a value that is not a number
    contributes that row to neither the average nor its denominator, and reporting the
    larger figure would overstate what the average is based on."""
    out = breakdown(
        admin, dataset, group_by="tozeret_nm", source="raw", limit=50,
        measure_column="shnat_yitzur", agg="avg",
    )
    expected = {k: len(v) for k, v in _numeric_by(oracle, "tozeret_nm", "shnat_yitzur").items()}
    got = {("__unspecified__" if i["unspecified"] else i["value"]): i["count"] for i in out["items"]}
    assert got == expected


def test_a_non_numeric_year_is_excluded_rather_than_failing_the_query(admin, dataset, oracle):
    """The fixture holds a year that is not a number. It must neither error the request
    nor be read as a zero, which would drag the average down without saying so."""
    unparseable = [r for r in oracle if r["shnat_yitzur"] and not r["shnat_yitzur"].isdigit()]
    assert unparseable, "fixture no longer has a non-numeric year; this test is moot"

    out = breakdown(
        admin, dataset, group_by="tozeret_nm", source="raw", limit=50,
        measure_column="shnat_yitzur", agg="min",
    )
    # Every value in the file that does parse is a plausible year; a zero here would mean
    # the unparseable one had been cast rather than skipped.
    assert all(i["measure"] >= 1900 for i in out["items"])


def test_the_default_is_still_a_plain_count(admin, dataset, oracle):
    """Every breakdown built before this feature existed must be unaffected."""
    out = breakdown(admin, dataset, group_by="baalut", source="raw", limit=50)
    assert out["agg"] == "count"
    assert out["measure_column"] is None
    assert all(i["measure"] is None for i in out["items"])
    assert sum(i["count"] for i in out["items"]) == out["total"] == len(oracle)


def test_the_request_is_echoed_back(admin, dataset):
    out = breakdown(
        admin, dataset, group_by="baalut", source="raw",
        measure_column="shnat_yitzur", agg="median",
    )
    assert out["measure_column"] == "shnat_yitzur"
    assert out["agg"] == "median"


def test_buckets_are_ordered_by_the_measure(admin, dataset):
    out = breakdown(
        admin, dataset, group_by="tozeret_nm", source="raw", limit=50,
        measure_column="shnat_yitzur", agg="avg",
    )
    got = [i["measure"] for i in out["items"]]
    assert got == sorted(got, reverse=True)


def test_no_other_bucket_is_invented_for_a_measure(admin, dataset):
    """An average of everything else describes a heap of unrelated categories. The list
    is cut and says so, rather than folding the tail into a figure nobody can act on."""
    out = breakdown(
        admin, dataset, group_by="tozeret_nm", source="raw", limit=2,
        measure_column="shnat_yitzur", agg="avg",
    )
    assert out["truncated"] is True
    assert all(not i["other"] for i in out["items"])


def test_an_aggregate_without_a_measure_column_is_refused(admin, dataset):
    r = admin.post(
        f"/api/datasets/{dataset}/statistics",
        json={"group_by": "baalut", "source": "raw", "agg": "avg"},
    )
    assert r.status_code == 400, r.text


def test_a_measure_column_with_count_is_refused(admin, dataset):
    """Counting rows while naming a column to measure returns a number that looks like
    the one asked for and is not - so it is refused rather than quietly answered."""
    r = admin.post(
        f"/api/datasets/{dataset}/statistics",
        json={"group_by": "baalut", "source": "raw",
              "measure_column": "shnat_yitzur", "agg": "count"},
    )
    assert r.status_code == 400, r.text


def test_an_unknown_measure_column_is_refused(admin, dataset):
    r = admin.post(
        f"/api/datasets/{dataset}/statistics",
        json={"group_by": "baalut", "source": "raw",
              "measure_column": "no_such_column", "agg": "avg"},
    )
    assert r.status_code == 400, r.text


def test_a_measure_over_a_text_column_reports_nothing_rather_than_erroring(admin, dataset):
    """Colour holds no numbers at all. Every bucket's aggregate is null, so no bucket
    survives - an empty result, not a 500."""
    out = breakdown(
        admin, dataset, group_by="baalut", source="raw", limit=50,
        measure_column="tzeva_rechev", agg="avg",
    )
    assert out["items"] == []


def test_filters_still_narrow_a_measured_breakdown(admin, dataset, oracle):
    out = breakdown(
        admin, dataset, group_by="baalut", source="raw", limit=50,
        measure_column="shnat_yitzur", agg="avg",
        filters=[{"column": "sug_delek_nm", "op": "eq", "value": "בנזין"}],
    )
    subset = [r for r in oracle if r["sug_delek_nm"] == "בנזין"]
    expected = {k: statistics.fmean(v) for k, v in _numeric_by(subset, "baalut", "shnat_yitzur").items()}
    got = _measures(out)
    assert got.keys() == expected.keys()
    for key, value in expected.items():
        assert got[key] == pytest.approx(value)
