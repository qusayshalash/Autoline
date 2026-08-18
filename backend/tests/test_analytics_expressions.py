"""The grouping expressions, checked as text.

The bucket expression decides what a row is counted under, so it is the single line that
determines whether blanks become a visible category or disappear. It is pure, so it is
tested here rather than through a query.
"""

import pytest

from app.models.schemas import FilterRule, PivotQuery, StatisticsQuery
from app.services import analytics


def test_value_buckets_fold_blank_and_whitespace_into_one_null():
    """Blanks arrive as '', '   ' and NULL from the same real file. All three have to
    land in the same bucket, or "unspecified" is reported three times with three
    different counts."""
    expr = analytics._bucket_expr("ramat_gimur", "value", "year")
    assert expr == 'NULLIF(TRIM("ramat_gimur"), \'\')'


def test_value_bucket_quotes_the_column():
    assert analytics._bucket_expr('weird"name', "value", "year").startswith('NULLIF(TRIM("weird""name")')


@pytest.mark.parametrize("granularity,fmt", [("year", "%Y"), ("month", "%Y-%m"), ("day", "%Y-%m-%d")])
def test_date_buckets_truncate_and_format_per_granularity(granularity, fmt):
    expr = analytics._bucket_expr("tarich", "date", granularity, date_parse="PARSED")
    assert f"date_trunc('{granularity}', PARSED)" in expr
    assert f"'{fmt}'" in expr


def test_an_unknown_granularity_falls_back_to_year_rather_than_breaking_the_query():
    expr = analytics._bucket_expr("tarich", "date", "fortnight", date_parse="PARSED")
    assert "date_trunc('year'" in expr


def test_where_is_empty_when_nothing_was_asked_for():
    sql, params = analytics._build_where(StatisticsQuery(group_by="tozeret_nm"), ["tozeret_nm"])
    assert sql == ""
    assert params == []


def test_search_and_filters_are_both_applied_and_parenthesised():
    """Each clause is wrapped before being joined: an unparenthesised OR inside one
    filter would otherwise swallow the rest of the WHERE."""
    q = StatisticsQuery(
        group_by="tozeret_nm",
        search="kia",
        filters=[FilterRule(column="ramat_gimur", op="is_null")],
    )
    sql, params = analytics._build_where(q, ["tozeret_nm", "ramat_gimur"])
    assert sql.startswith("(") and ") AND (" in sql
    assert params[0] == "%kia%"


def test_a_pivot_and_a_breakdown_build_the_same_subset():
    """The cross-tab must describe exactly the rows the one-dimensional breakdown would,
    or switching modes appears to change the data."""
    filters = [FilterRule(column="tozeret_nm", op="starts_with", value="kia")]
    columns = ["tozeret_nm", "sug_delek_nm"]
    a = analytics._build_where(
        StatisticsQuery(group_by="tozeret_nm", search="x", filters=filters), columns
    )
    b = analytics._build_where(
        PivotQuery(row_column="tozeret_nm", column_column="sug_delek_nm", search="x", filters=filters),
        columns,
    )
    assert a == b


def test_a_filter_on_an_unlisted_column_is_refused():
    with pytest.raises(ValueError, match="Unknown column"):
        analytics._build_where(
            StatisticsQuery(
                group_by="tozeret_nm", filters=[FilterRule(column="secret", op="eq", value="x")]
            ),
            ["tozeret_nm"],
        )
