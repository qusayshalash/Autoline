"""Cross-tabs.

The cross-tab never materialises the full matrix - it fetches the top rows, the top
columns, and only the cells inside that cut, then derives the "other" bands by
subtraction. That arithmetic is the entire correctness story: if it is off by one, the
totals still look plausible, which is exactly why it is checked against the file rather
than against itself.
"""

import synthetic
from helpers import pivot


def _cross(oracle, row_col, col_col):
    """The matrix according to Python, with blanks named the way the API names them."""
    out = {}
    for r in oracle:
        key = (r[row_col] or "", r[col_col] or "")
        out[key] = out.get(key, 0) + 1
    return out


def _label(header):
    """The API distinguishes a blank category from the aggregate band by flag, not by
    value - both come back with an empty string."""
    if header["other"]:
        return "__other__"
    if header["unspecified"]:
        return ""
    return header["value"]


def _matrix(out):
    cols = [_label(c) for c in out["columns"]]
    return {
        (_label(r["header"]), cols[i]): cell
        for r in out["rows"]
        for i, cell in enumerate(r["cells"])
    }


def test_cells_match_the_file(admin, dataset, oracle):
    out = pivot(admin, dataset, row_column="baalut", column_column="sug_delek_nm",
                source="raw", row_limit=25, column_limit=25)
    expected = _cross(oracle, "baalut", "sug_delek_nm")
    got = _matrix(out)
    assert not out["rows_truncated"] and not out["columns_truncated"]
    for key, count in got.items():
        assert count == expected.get(key, 0), key
    assert sum(got.values()) == len(oracle)


def test_every_row_closes_against_its_own_total(admin, dataset):
    out = pivot(admin, dataset, row_column="baalut", column_column="sug_delek_nm",
                source="raw", row_limit=25, column_limit=25)
    for row in out["rows"]:
        assert sum(row["cells"]) == row["header"]["total"], _label(row["header"])


def test_every_column_closes_against_its_own_total(admin, dataset):
    out = pivot(admin, dataset, row_column="baalut", column_column="sug_delek_nm",
                source="raw", row_limit=25, column_limit=25)
    for i, col in enumerate(out["columns"]):
        assert sum(r["cells"][i] for r in out["rows"]) == col["total"], _label(col)


def test_the_whole_matrix_closes_against_the_grand_total(admin, dataset, oracle):
    out = pivot(admin, dataset, row_column="baalut", column_column="sug_delek_nm",
                source="raw", row_limit=25, column_limit=25)
    assert sum(sum(r["cells"]) for r in out["rows"]) == out["total"] == len(oracle)


def test_axis_totals_match_the_one_dimensional_breakdown(admin, dataset, oracle):
    """A row total in the cross-tab and a bucket count in the breakdown are the same
    number arrived at by two different queries. If they disagree, one of them is wrong.
    """
    out = pivot(admin, dataset, row_column="baalut", column_column="sug_delek_nm",
                source="raw", row_limit=25, column_limit=25)
    per_owner = {}
    for r in oracle:
        key = r["baalut"] or ""
        per_owner[key] = per_owner.get(key, 0) + 1
    for row in out["rows"]:
        assert row["header"]["total"] == per_owner[_label(row["header"])]


def test_folding_both_axes_still_closes_exactly(admin, dataset, oracle):
    """The hard case. With both axes cut, the corner cell belongs to no shown row and no
    shown column, and is recovered by inclusion-exclusion. Off-by-one here is invisible
    in any single row or column - only the grand total catches it.
    """
    out = pivot(admin, dataset, row_column="tozeret_nm", column_column="sug_delek_nm",
                source="raw", row_limit=2, column_limit=2)
    assert out["rows_truncated"] and out["columns_truncated"]

    for row in out["rows"]:
        assert sum(row["cells"]) == row["header"]["total"], _label(row["header"])
    for i, col in enumerate(out["columns"]):
        assert sum(r["cells"][i] for r in out["rows"]) == col["total"], _label(col)
    assert sum(sum(r["cells"]) for r in out["rows"]) == out["total"] == len(oracle)


def test_the_other_bands_are_exact_not_estimated(admin, dataset, oracle):
    """The remainder must equal the real sum of everything folded away, to the row."""
    out = pivot(admin, dataset, row_column="tozeret_nm", column_column="sug_delek_nm",
                source="raw", row_limit=2, column_limit=25)
    kept = {_label(r["header"]) for r in out["rows"] if not r["header"]["other"]}
    other_row = next(r for r in out["rows"] if r["header"]["other"])

    expected_folded = sum(1 for r in oracle if (r["tozeret_nm"] or "") not in kept)
    assert other_row["header"]["total"] == expected_folded

    # and cell by cell, not only in total
    expected_cells = {}
    for r in oracle:
        if (r["tozeret_nm"] or "") not in kept:
            key = r["sug_delek_nm"] or ""
            expected_cells[key] = expected_cells.get(key, 0) + 1
    for i, col in enumerate(out["columns"]):
        assert other_row["cells"][i] == expected_cells.get(_label(col), 0), _label(col)


def test_blanks_are_a_band_of_their_own_on_both_axes(admin, dataset, oracle):
    out = pivot(admin, dataset, row_column="tozeret_nm", column_column="sug_delek_nm",
                source="raw", row_limit=25, column_limit=25)
    row_blank = next(r for r in out["rows"] if r["header"]["unspecified"])
    col_blank_i = next(i for i, c in enumerate(out["columns"]) if c["unspecified"])

    assert row_blank["header"]["total"] == sum(1 for r in oracle if r["tozeret_nm"] == "")
    assert (
        sum(r["cells"][col_blank_i] for r in out["rows"])
        == sum(1 for r in oracle if r["sug_delek_nm"] == "")
    )


def test_swapping_the_axes_transposes_the_matrix(admin, dataset):
    """The same data seen the other way round. Any asymmetry between the row path and the
    column path shows up here and nowhere else.
    """
    a = pivot(admin, dataset, row_column="baalut", column_column="sug_delek_nm",
              source="raw", row_limit=25, column_limit=25)
    b = pivot(admin, dataset, row_column="sug_delek_nm", column_column="baalut",
              source="raw", row_limit=25, column_limit=25)
    ma, mb = _matrix(a), _matrix(b)
    assert a["total"] == b["total"]
    assert ma == {(c, r): v for (r, c), v in mb.items()}


def test_filters_narrow_the_matrix_and_the_total(admin, dataset, oracle):
    out = pivot(admin, dataset, row_column="baalut", column_column="sug_delek_nm",
                source="raw", row_limit=25, column_limit=25,
                filters=[{"column": "shnat_yitzur", "op": "eq", "value": "2020"}])
    subset = [r for r in oracle if r["shnat_yitzur"] == "2020"]
    assert out["total"] == len(subset)
    assert out["grand_total"] == len(oracle)
    # the matrix is dense - a combination that does not occur comes back as an explicit
    # zero rather than a missing cell - so the oracle side supplies the zeros
    expected = _cross(subset, "baalut", "sug_delek_nm")
    got = _matrix(out)
    assert got == {key: expected.get(key, 0) for key in got}
    assert sum(got.values()) == len(subset)


def test_a_filter_that_matches_nothing_gives_an_empty_matrix_not_an_error(admin, dataset):
    out = pivot(admin, dataset, row_column="baalut", column_column="sug_delek_nm",
                source="raw",
                filters=[{"column": "shnat_yitzur", "op": "eq", "value": "1899"}])
    assert out["total"] == 0
    assert out["rows"] == []
    assert out["columns"] == []


def test_a_wide_sparse_pairing_still_closes(admin, dataset, oracle):
    """The identifier column has one distinct value per row, so almost the entire axis is
    folded away. This is the shape where an "other" band computed loosely goes wrong.
    """
    out = pivot(admin, dataset, row_column="mispar_rechev", column_column="sug_delek_nm",
                source="raw", row_limit=5, column_limit=3)
    assert out["rows_truncated"]
    for row in out["rows"]:
        assert sum(row["cells"]) == row["header"]["total"]
    for i, col in enumerate(out["columns"]):
        assert sum(r["cells"][i] for r in out["rows"]) == col["total"]
    assert sum(sum(r["cells"]) for r in out["rows"]) == len(oracle)


def test_the_same_column_on_both_axes_is_refused(admin, dataset):
    """A column crossed with itself is a diagonal - no information, and a confusing
    screen. Better refused at the edge than rendered.
    """
    r = admin.post(
        f"/api/datasets/{dataset}/pivot",
        json={"row_column": "baalut", "column_column": "baalut", "source": "raw"},
    )
    assert r.status_code == 400, r.text


def test_an_unknown_column_is_a_400(admin, dataset):
    r = admin.post(
        f"/api/datasets/{dataset}/pivot",
        json={"row_column": "no_such", "column_column": "baalut", "source": "raw"},
    )
    assert r.status_code == 400, r.text


def test_limits_over_the_cap_are_refused(admin, dataset):
    r = admin.post(
        f"/api/datasets/{dataset}/pivot",
        json={"row_column": "baalut", "column_column": "sug_delek_nm",
              "source": "raw", "row_limit": 5000},
    )
    assert r.status_code == 422, r.text


def test_distinct_axis_sizes_are_reported(admin, dataset, oracle):
    out = pivot(admin, dataset, row_column="tozeret_nm", column_column="sug_delek_nm",
                source="raw", row_limit=2, column_limit=2)
    assert out["distinct_rows"] == len({r["tozeret_nm"] for r in oracle})
    assert out["distinct_columns"] == len({r["sug_delek_nm"] for r in oracle})
