"""Filtering, searching, sorting and paging the grid.

Expected counts come from the oracle - the same file read by Python - so a filter that
is merely plausible still fails. A blank field is NULL once imported (see
test_ingestion), so the oracle side treats '' and missing as the same absence.
"""

import synthetic
from helpers import page, rows_as_dicts, total


def _count(oracle, column, predicate) -> int:
    return sum(1 for r in oracle if predicate(r[column]))


def test_total_matches_the_file(admin, dataset, oracle):
    assert total(admin, dataset, source="raw") == len(oracle)


def test_eq_counts_match_the_file(admin, dataset, oracle):
    for value in ["בנזין", "דיזל", "חשמל", "היברידי"]:
        got = total(
            admin, dataset, source="raw",
            filters=[{"column": "sug_delek_nm", "op": "eq", "value": value}],
        )
        assert got == _count(oracle, "sug_delek_nm", lambda v: v == value), value


def test_neq_excludes_missing_values_as_well(admin, dataset, oracle):
    """A comparison against NULL is NULL, and NULL is not true, so rows with no value are
    excluded from neq. Not a bug, but it means eq and neq do not partition the table -
    stated here so nobody later "fixes" a total that appears not to add up.
    """
    eq = total(
        admin, dataset, source="raw",
        filters=[{"column": "sug_delek_nm", "op": "eq", "value": "בנזין"}],
    )
    neq = total(
        admin, dataset, source="raw",
        filters=[{"column": "sug_delek_nm", "op": "neq", "value": "בנזין"}],
    )
    blanks = _count(oracle, "sug_delek_nm", lambda v: v == "")
    assert eq + neq + blanks == len(oracle)
    assert blanks > 0  # otherwise this test proves nothing


def test_starts_with_avoids_the_country_name_trap(admin, dataset, oracle):
    """The reason starts_with exists. In Hebrew the maker's name is the tail of a
    country's name, so a contains search for the maker also returns cars assembled there.
    """
    contains = total(
        admin, dataset, source="raw",
        filters=[{"column": "tozeret_nm", "op": "contains", "value": "קיה"}],
    )
    starts = total(
        admin, dataset, source="raw",
        filters=[{"column": "tozeret_nm", "op": "starts_with", "value": "קיה"}],
    )
    kia = _count(oracle, "tozeret_nm", lambda v: v == synthetic.KIA)
    turkey = _count(oracle, "tozeret_nm", lambda v: v == synthetic.TURKEY)

    assert starts == kia
    assert contains == kia + turkey
    assert contains > starts, "the trap is not present in the fixture"


def test_ends_with_matches_the_tail_only(admin, dataset, oracle):
    got = total(
        admin, dataset, source="raw",
        filters=[{"column": "tozeret_nm", "op": "ends_with", "value": "יבוא"}],
    )
    assert got == _count(oracle, "tozeret_nm", lambda v: v.endswith("יבוא"))


def test_wildcards_typed_by_the_user_are_literal(admin, dataset):
    """A value containing a percent sign must match that character, not "anything".
    Unescaped, this filter would return every row in the table.
    """
    got = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "tzeva_rechev", "op": "contains", "value": "50%_"}],
    )
    assert len(got) == 1
    assert got[0]["tzeva_rechev"] == "50%_ספיישל"


def test_a_bare_percent_does_not_match_everything(admin, dataset, oracle):
    got = total(
        admin, dataset, source="raw",
        filters=[{"column": "tzeva_rechev", "op": "contains", "value": "%"}],
    )
    assert got == _count(oracle, "tzeva_rechev", lambda v: "%" in v)
    assert got < len(oracle)


def test_numeric_comparison_ignores_a_non_numeric_value(admin, dataset, oracle):
    """The year column is text and holds one non-year. TRY_CAST makes it NULL, so it is
    excluded rather than sorting somewhere arbitrary or failing the query.
    """
    got = total(
        admin, dataset, source="raw",
        filters=[{"column": "shnat_yitzur", "op": "gte", "value": "2018"}],
    )
    expected = _count(oracle, "shnat_yitzur", lambda v: v.isdigit() and int(v) >= 2018)
    assert got == expected
    assert any(r["shnat_yitzur"] and not r["shnat_yitzur"].isdigit() for r in oracle)


def test_numeric_comparison_orders_by_value_not_by_text(admin, dataset, oracle):
    """As text, 2020 sorts after 19999. Casting is what makes a year range mean anything."""
    got = total(
        admin, dataset, source="raw",
        filters=[{"column": "shnat_yitzur", "op": "gt", "value": "2021"}],
    )
    assert got == _count(oracle, "shnat_yitzur", lambda v: v.isdigit() and int(v) > 2021)


def test_is_null_counts_blanks(admin, dataset, oracle):
    got = total(
        admin, dataset, source="raw",
        filters=[{"column": "ramat_gimur", "op": "is_null"}],
    )
    assert got == _count(oracle, "ramat_gimur", lambda v: v == "")


def test_is_null_and_not_null_partition_the_table(admin, dataset, oracle):
    """These two must add up exactly - unlike eq and neq - because both branches name the
    missing case explicitly.
    """
    a = total(admin, dataset, source="raw", filters=[{"column": "ramat_gimur", "op": "is_null"}])
    b = total(admin, dataset, source="raw", filters=[{"column": "ramat_gimur", "op": "not_null"}])
    assert a + b == len(oracle)


def test_in_filter_matches_the_union(admin, dataset, oracle):
    values = ["בנזין", "חשמל"]
    got = total(
        admin, dataset, source="raw",
        filters=[{"column": "sug_delek_nm", "op": "in", "values": values}],
    )
    assert got == _count(oracle, "sug_delek_nm", lambda v: v in values)


def test_an_empty_in_selection_does_not_empty_the_grid(admin, dataset, oracle):
    got = total(
        admin, dataset, source="raw",
        filters=[{"column": "sug_delek_nm", "op": "in", "values": []}],
    )
    assert got == len(oracle)


def test_filters_combine_as_and(admin, dataset, oracle):
    got = total(
        admin, dataset, source="raw",
        filters=[
            {"column": "sug_delek_nm", "op": "eq", "value": "דיזל"},
            {"column": "baalut", "op": "eq", "value": "חברה"},
        ],
    )
    expected = sum(1 for r in oracle if r["sug_delek_nm"] == "דיזל" and r["baalut"] == "חברה")
    assert got == expected
    assert expected > 0


def test_search_spans_every_column(admin, dataset, oracle):
    got = total(admin, dataset, source="raw", search="ליסינג")
    expected = sum(1 for r in oracle if any("ליסינג" in v for v in r.values()))
    assert got == expected


def test_search_and_filter_intersect(admin, dataset, oracle):
    got = total(
        admin, dataset, source="raw",
        search="ליסינג",
        filters=[{"column": "sug_delek_nm", "op": "eq", "value": "חשמל"}],
    )
    expected = sum(
        1 for r in oracle
        if any("ליסינג" in v for v in r.values()) and r["sug_delek_nm"] == "חשמל"
    )
    assert got == expected
    assert expected > 0


def test_paging_covers_every_row_exactly_once(admin, dataset, oracle):
    """The failure this catches is an off-by-one in OFFSET, which drops or repeats one row
    per page - invisible on page one and unnoticeable in a spot check.
    """
    seen = []
    page_size = 37  # deliberately not a divisor of the row count
    p = 1
    while True:
        data = page(admin, dataset, source="raw", page=p, page_size=page_size,
                    sort_by="mispar_rechev", sort_dir="asc")
        if not data["rows"]:
            break
        assert len(data["rows"]) <= page_size
        seen.extend(row[0] for row in data["rows"])
        p += 1
        assert p < 100, "paging did not terminate"

    assert len(seen) == len(oracle)
    # the duplicate pair shares an id, so this compares multisets, not sets
    assert sorted(seen) == sorted(r["mispar_rechev"] for r in oracle)


def test_sorting_is_reversible(admin, dataset):
    asc = [r["mispar_rechev"] for r in rows_as_dicts(
        admin, dataset, source="raw", sort_by="mispar_rechev", sort_dir="asc")]
    desc = [r["mispar_rechev"] for r in rows_as_dicts(
        admin, dataset, source="raw", sort_by="mispar_rechev", sort_dir="desc")]
    assert asc == list(reversed(desc))


def test_sorting_a_text_column_is_lexicographic(admin, dataset):
    """Identifiers are text, and text sorts lexicographically - which lands in numeric
    order only because the zero padding is intact. Another reason it must be preserved.
    """
    ids = [r["mispar_rechev"] for r in rows_as_dicts(
        admin, dataset, source="raw", sort_by="mispar_rechev", sort_dir="asc")]
    assert ids == sorted(ids)


def test_distinct_values_lists_every_category_with_counts(admin, dataset, oracle):
    r = admin.get(
        f"/api/datasets/{dataset}/data/distinct-values",
        params={"column": "sug_delek_nm", "source": "raw"},
    )
    assert r.status_code == 200, r.text
    got = {v["value"]: v["count"] for v in r.json()["values"]}
    for value in ["בנזין", "דיזל", "חשמל", "היברידי"]:
        assert got[value] == _count(oracle, "sug_delek_nm", lambda v: v == value)


def test_grouping_counts_match_the_file(admin, dataset, oracle):
    r = admin.post(
        f"/api/datasets/{dataset}/group",
        json={"column": "baalut", "source": "raw", "page_size": 100},
    )
    assert r.status_code == 200, r.text
    got = {g["value"]: g["count"] for g in r.json()["groups"]}
    for value in ["פרטי", "חברה", "ליסינג"]:
        assert got[value] == _count(oracle, "baalut", lambda v: v == value)
    assert sum(got.values()) == len(oracle)


def test_an_unknown_filter_column_is_a_400_not_a_500(admin, dataset):
    r = admin.post(
        f"/api/datasets/{dataset}/data",
        json={"source": "raw", "filters": [{"column": "no_such", "op": "eq", "value": "x"}]},
    )
    assert r.status_code == 400, r.text


def test_an_unknown_sort_column_is_a_400_not_a_500(admin, dataset):
    r = admin.post(f"/api/datasets/{dataset}/data", json={"source": "raw", "sort_by": "no_such"})
    assert r.status_code == 400, r.text


def test_page_size_over_the_cap_is_clamped_and_reported(admin, dataset):
    """An oversized request is served at the cap rather than refused - but the response
    states the size it actually used, so the caller is never misled about what it got.
    The guarantee that matters is that no request can ask for an unbounded page.
    """
    from app.config import settings

    r = admin.post(f"/api/datasets/{dataset}/data", json={"source": "raw", "page_size": 999999})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["page_size"] == settings.max_page_size
    assert len(body["rows"]) <= settings.max_page_size


def test_a_page_size_of_zero_returns_a_row_rather_than_an_empty_page(admin, dataset):
    """Clamped at the bottom too. Zero would otherwise mean LIMIT 0 - an empty grid that
    looks like an empty file.
    """
    r = admin.post(f"/api/datasets/{dataset}/data", json={"source": "raw", "page_size": 0})
    assert r.status_code == 200, r.text
    assert r.json()["page_size"] >= 1
    assert len(r.json()["rows"]) >= 1


# ---- narrowing the search ----------------------------------------------------------


def test_searching_named_columns_only_looks_there(admin, dataset, oracle):
    """The point of narrowing: a term that appears in two columns, searched in one."""
    everywhere = total(admin, dataset, source="raw", search="בנזין")
    one_column = total(
        admin, dataset, source="raw", search="בנזין", search_columns=["sug_delek_nm"]
    )
    expected = sum(1 for r in oracle if "בנזין" in r["sug_delek_nm"])
    assert one_column == expected
    assert everywhere >= one_column


def test_narrowing_can_exclude_a_match(admin, dataset, oracle):
    """Searching a column the term is not in finds nothing, even though the file
    contains it - which is the whole behaviour being bought."""
    found = total(admin, dataset, source="raw", search="בנזין", search_columns=["baalut"])
    assert found == 0
    assert total(admin, dataset, source="raw", search="בנזין") > 0


def test_no_columns_named_still_searches_everything(admin, dataset):
    """The default has to stay what it was. A search that quietly stopped looking
    somewhere would return nothing and give no reason."""
    everywhere = total(admin, dataset, source="raw", search="ליסינג")
    assert total(admin, dataset, source="raw", search="ליסינג", search_columns=None) == everywhere
    assert total(admin, dataset, source="raw", search="ליסינג", search_columns=[]) == everywhere


def test_several_columns_are_combined(admin, dataset, oracle):
    got = total(
        admin, dataset, source="raw", search="קיה",
        search_columns=["tozeret_nm", "ramat_gimur"],
    )
    expected = sum(
        1 for r in oracle if "קיה" in r["tozeret_nm"] or "קיה" in r["ramat_gimur"]
    )
    assert got == expected


def test_an_unknown_search_column_is_a_400(admin, dataset):
    r = admin.post(
        f"/api/datasets/{dataset}/data",
        json={"source": "raw", "search": "x", "search_columns": ["no_such_column"]},
    )
    assert r.status_code == 400, r.text


def test_the_breakdown_searches_the_same_columns_as_the_grid(admin, dataset):
    """The statistics screen promises it describes the rows the grid would show. That
    promise breaks if the two search different columns."""
    narrowed = {"search": "קיה", "search_columns": ["tozeret_nm"], "source": "raw"}
    grid = total(admin, dataset, **narrowed)

    r = admin.post(
        f"/api/datasets/{dataset}/statistics", json={"group_by": "baalut", **narrowed}
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == grid


def test_the_pivot_searches_the_same_columns_too(admin, dataset):
    narrowed = {"search": "קיה", "search_columns": ["tozeret_nm"], "source": "raw"}
    grid = total(admin, dataset, **narrowed)

    r = admin.post(
        f"/api/datasets/{dataset}/pivot",
        json={"row_column": "baalut", "column_column": "sug_delek_nm", **narrowed},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == grid


def test_grouping_honours_the_narrowed_search(admin, dataset):
    narrowed = {"search": "קיה", "search_columns": ["tozeret_nm"], "source": "raw"}
    grid = total(admin, dataset, **narrowed)

    r = admin.post(
        f"/api/datasets/{dataset}/group", json={"column": "baalut", "page_size": 100, **narrowed}
    )
    assert r.status_code == 200, r.text
    assert sum(g["count"] for g in r.json()["groups"]) == grid
