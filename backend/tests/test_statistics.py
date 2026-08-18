"""Breakdowns.

The property that has to hold no matter how the buckets are folded: the parts add up to
the whole. A breakdown that loses rows into a hidden remainder is worse than one that
errors, because it looks like an answer.
"""

import synthetic
from helpers import breakdown, buckets


def _counts(oracle, column):
    out = {}
    for r in oracle:
        key = "__unspecified__" if r[column] == "" else r[column]
        out[key] = out.get(key, 0) + 1
    return out


def test_bucket_counts_match_the_file(admin, dataset, oracle):
    got = buckets(breakdown(admin, dataset, group_by="sug_delek_nm", source="raw", limit=50))
    assert got == _counts(oracle, "sug_delek_nm")


def test_the_buckets_sum_to_the_total(admin, dataset, oracle):
    out = breakdown(admin, dataset, group_by="tozeret_nm", source="raw", limit=50)
    assert out["total"] == len(oracle)
    assert sum(i["count"] for i in out["items"]) == out["total"]


def test_blanks_are_a_visible_bucket_not_a_silent_drop(admin, dataset, oracle):
    """The single most valuable guarantee in this file. Missing values are a finding, not
    noise - a column that is 40% empty must say so.
    """
    out = breakdown(admin, dataset, group_by="ramat_gimur", source="raw", limit=50)
    got = buckets(out)
    expected_blanks = sum(1 for r in oracle if r["ramat_gimur"] == "")
    assert expected_blanks > 0
    assert got["__unspecified__"] == expected_blanks
    assert sum(got.values()) == len(oracle)


def test_percentages_are_shares_of_the_total(admin, dataset, oracle):
    out = breakdown(admin, dataset, group_by="baalut", source="raw", limit=50)
    for item in out["items"]:
        assert abs(item["percentage"] - item["count"] * 100 / out["total"]) < 0.01
    assert abs(sum(i["percentage"] for i in out["items"]) - 100) < 0.05


def test_a_low_limit_folds_the_tail_into_other_without_losing_rows(admin, dataset, oracle):
    """Truncation is where a total quietly stops adding up. The remainder bucket is
    computed by subtraction, so it has to close exactly however many categories are cut.
    """
    full = buckets(breakdown(admin, dataset, group_by="tozeret_nm", source="raw", limit=50))
    full.pop("__other__", None)

    out = breakdown(admin, dataset, group_by="tozeret_nm", source="raw", limit=2)
    got = buckets(out)
    assert out["truncated"] is True
    assert "__other__" in got
    assert sum(got.values()) == len(oracle)
    # the two kept buckets are the two largest
    kept = {k: v for k, v in got.items() if k != "__other__"}
    biggest = sorted(full.values(), reverse=True)[:2]
    assert sorted(kept.values(), reverse=True) == biggest


def test_distinct_count_is_reported_even_when_truncated(admin, dataset, oracle):
    """Otherwise "top 2 of 5" reads as "there are 2"."""
    out = breakdown(admin, dataset, group_by="tozeret_nm", source="raw", limit=2)
    distinct_in_file = len({r["tozeret_nm"] for r in oracle})
    assert out["distinct_values"] == distinct_in_file


def test_the_distinct_count_includes_the_unspecified_bucket(admin, dataset, oracle):
    """The count is what the screen's "showing N of M values" note is built from, and the
    unspecified bucket is one of the rows on screen. Counting buckets while excluding one
    that is displayed makes the page contradict itself.
    """
    out = breakdown(admin, dataset, group_by="tozeret_nm", source="raw", limit=50)
    shown_buckets = len([i for i in out["items"] if not i["other"]])
    assert out["distinct_values"] == shown_buckets
    assert any(i["unspecified"] for i in out["items"]), "the fixture should have blanks here"


def test_filters_narrow_the_breakdown_and_the_total_with_it(admin, dataset, oracle):
    out = breakdown(
        admin, dataset, group_by="sug_delek_nm", source="raw", limit=50,
        filters=[{"column": "baalut", "op": "eq", "value": "חברה"}],
    )
    subset = [r for r in oracle if r["baalut"] == "חברה"]
    assert out["total"] == len(subset)
    assert out["grand_total"] == len(oracle), "grand_total must stay the whole file"
    assert buckets(out) == _counts(subset, "sug_delek_nm")


def test_sorting_by_value_is_not_sorting_by_count(admin, dataset):
    """Chronological order for years; popularity order for categories. Both are needed,
    and a breakdown that silently ignores the request is the failure mode.
    """
    by_count = breakdown(admin, dataset, group_by="shnat_yitzur", source="raw", limit=50,
                         sort="count")
    by_value = breakdown(admin, dataset, group_by="shnat_yitzur", source="raw", limit=50,
                         sort="value")
    counts = [i["count"] for i in by_count["items"] if not i["other"]]
    assert counts == sorted(counts, reverse=True)

    labels = [i["value"] for i in by_value["items"] if not (i["other"] or i["unspecified"])]
    assert labels == sorted(labels)
    assert by_count["items"] != by_value["items"]


def test_both_shapes_of_the_endpoint_agree(admin, dataset):
    """The page uses POST; links and exports use GET. They must not diverge."""
    post = breakdown(admin, dataset, group_by="baalut", source="raw", limit=50)
    r = admin.get(
        f"/api/datasets/{dataset}/statistics",
        params={"group_by": "baalut", "source": "raw", "limit": 50},
    )
    assert r.status_code == 200, r.text
    get = r.json()
    assert buckets(post) == buckets(get)
    assert post["total"] == get["total"]


def test_column_suggestions_cover_every_column(admin, dataset):
    r = admin.get(f"/api/datasets/{dataset}/statistics/columns", params={"source": "raw"})
    assert r.status_code == 200, r.text
    names = [c["name"] for c in r.json()]
    assert names == synthetic.COLUMNS


def test_an_unknown_group_column_is_a_400(admin, dataset):
    r = admin.post(
        f"/api/datasets/{dataset}/statistics",
        json={"group_by": "no_such", "source": "raw"},
    )
    assert r.status_code == 400, r.text


def test_a_limit_over_the_cap_is_refused(admin, dataset):
    r = admin.post(
        f"/api/datasets/{dataset}/statistics",
        json={"group_by": "baalut", "source": "raw", "limit": 100000},
    )
    assert r.status_code == 422, r.text
