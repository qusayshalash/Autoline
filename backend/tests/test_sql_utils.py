"""Dynamic SQL construction. No database - these are about the text produced, and the
one rule the whole module rests on: identifiers are validated then quoted, values are
never interpolated.
"""

import pytest

from app.models.schemas import FilterRule
from app.services import sql_utils

VALID = {"tozeret_nm", "sug_delek_nm", "shnat_yitzur", "weird\"name"}


def test_quote_ident_wraps_and_doubles_embedded_quotes():
    assert sql_utils.quote_ident("plain") == '"plain"'
    # a column literally named  a"b  must not be able to end the quoted identifier early
    assert sql_utils.quote_ident('a"b') == '"a""b"'


def test_quote_ident_neutralises_an_injection_attempt():
    """The payload survives as text but never as SQL: the only unescaped quotes in the
    result are the opening and closing ones, so the identifier cannot be closed early."""
    quoted = sql_utils.quote_ident('x"; DROP TABLE raw_data; --')
    assert quoted == '"x""; DROP TABLE raw_data; --"'
    inner = quoted[1:-1]
    assert '"' not in inner.replace('""', "")


# The LIKE escape character, spelled once so the tests below read as data rather
# than as a backslash-counting exercise.
BS = chr(92)


def test_escape_like_makes_wildcards_literal():
    assert sql_utils.escape_like("50%") == "50" + BS + "%"
    assert sql_utils.escape_like("a_b") == "a" + BS + "_b"
    assert sql_utils.escape_like("plain") == "plain"


def test_escape_like_escapes_the_escape_first():
    """Order matters: escaping the wildcards first would then escape the backslashes
    this function just inserted, turning them into literals and un-escaping the
    wildcards again."""
    assert sql_utils.escape_like(BS) == BS + BS
    # a backslash already in the value is escaped before the % gets its own, so the
    # added escape cannot be swallowed as the escape of the pre-existing backslash
    assert sql_utils.escape_like("100" + BS + "%") == "100" + BS + BS + BS + "%"


def test_unknown_column_is_rejected_not_interpolated():
    with pytest.raises(ValueError, match="Unknown column"):
        sql_utils.build_filter_sql(
            [FilterRule(column="no_such_column", op="eq", value="x")], VALID
        )


def test_unknown_column_in_validate_columns_lists_all_offenders():
    with pytest.raises(ValueError) as exc:
        sql_utils.validate_columns(["a", "tozeret_nm", "b"], VALID)
    assert "a" in str(exc.value) and "b" in str(exc.value)
    assert "tozeret_nm" not in str(exc.value)


def test_eq_binds_the_value_rather_than_inlining_it():
    sql, params = sql_utils.build_filter_sql(
        [FilterRule(column="tozeret_nm", op="eq", value="'; DROP TABLE raw_data; --")], VALID
    )
    assert sql == '"tozeret_nm" = ?'
    assert params == ["'; DROP TABLE raw_data; --"]
    assert "DROP" not in sql


@pytest.mark.parametrize("op,pattern", [
    ("contains", "%kia%"),
    ("starts_with", "kia%"),
    ("ends_with", "%kia"),
])
def test_text_operators_wrap_the_value_in_the_right_pattern(op, pattern):
    sql, params = sql_utils.build_filter_sql(
        [FilterRule(column="tozeret_nm", op=op, value="kia")], VALID
    )
    assert "ILIKE ? ESCAPE" in sql
    assert params == [pattern]


def test_text_operator_escapes_wildcards_inside_the_value():
    _, params = sql_utils.build_filter_sql(
        [FilterRule(column="tozeret_nm", op="contains", value="50%")], VALID
    )
    assert params == ["%50\%%"]  # the user's % is escaped, the pattern's are not


def test_is_null_treats_empty_string_as_missing():
    """The loader keeps every column VARCHAR, so a missing field arrives as '' at least
    as often as NULL. Only checking IS NULL would report almost nothing missing."""
    sql, params = sql_utils.build_filter_sql(
        [FilterRule(column="ramat_gimur", op="is_null")], {"ramat_gimur"}
    )
    assert sql == '("ramat_gimur" IS NULL OR "ramat_gimur" = \'\')'
    assert params == []


def test_not_null_is_the_exact_complement_of_is_null():
    is_null, _ = sql_utils.build_filter_sql(
        [FilterRule(column="ramat_gimur", op="is_null")], {"ramat_gimur"}
    )
    not_null, _ = sql_utils.build_filter_sql(
        [FilterRule(column="ramat_gimur", op="not_null")], {"ramat_gimur"}
    )
    assert is_null == '("ramat_gimur" IS NULL OR "ramat_gimur" = \'\')'
    assert not_null == '("ramat_gimur" IS NOT NULL AND "ramat_gimur" != \'\')'


@pytest.mark.parametrize("op,sign", [("gt", ">"), ("gte", ">="), ("lt", "<"), ("lte", "<=")])
def test_numeric_comparisons_cast_both_sides(op, sign):
    """Both sides go through TRY_CAST: the column is text, and comparing '9' to '10' as
    text puts 9 after 10."""
    sql, params = sql_utils.build_filter_sql(
        [FilterRule(column="shnat_yitzur", op=op, value="2020")], VALID
    )
    assert sql == f'TRY_CAST("shnat_yitzur" AS DOUBLE) {sign} TRY_CAST(? AS DOUBLE)'
    assert params == ["2020"]


def test_in_binds_one_placeholder_per_value():
    sql, params = sql_utils.build_filter_sql(
        [FilterRule(column="tozeret_nm", op="in", values=["a", "b", "c"])], VALID
    )
    assert sql == '"tozeret_nm" IN (?, ?, ?)'
    assert params == ["a", "b", "c"]


def test_in_with_no_values_adds_no_constraint():
    """An empty selection means "no filter", not "match nothing" - the alternative is a
    grid that silently empties itself when the last checkbox is cleared."""
    sql, params = sql_utils.build_filter_sql(
        [FilterRule(column="tozeret_nm", op="in", values=[])], VALID
    )
    assert sql == ""
    assert params == []


def test_multiple_filters_are_conjoined_in_order():
    sql, params = sql_utils.build_filter_sql(
        [
            FilterRule(column="tozeret_nm", op="eq", value="kia"),
            FilterRule(column="shnat_yitzur", op="gte", value="2020"),
        ],
        VALID,
    )
    assert sql.count(" AND ") == 1
    assert params == ["kia", "2020"]


def test_search_spans_every_column_as_one_string():
    sql, params = sql_utils.build_search_sql("kia", ["tozeret_nm", "sug_delek_nm"])
    assert sql == 'concat_ws(\' \', "tozeret_nm", "sug_delek_nm") ILIKE ?'
    assert params == ["%kia%"]


def test_order_by_rejects_an_unknown_column():
    with pytest.raises(ValueError, match="Unknown column"):
        sql_utils.build_order_sql("no_such_column", "asc", VALID)


@pytest.mark.parametrize("given,expected", [("desc", "DESC"), ("asc", "ASC"), ("garbage", "ASC")])
def test_order_direction_defaults_to_ascending(given, expected):
    assert sql_utils.build_order_sql("tozeret_nm", given, VALID) == f'"tozeret_nm" {expected}'


def test_a_column_whose_name_contains_a_quote_survives_every_builder():
    """This column exists in VALID on purpose. A real CSV header can contain anything."""
    sql, _ = sql_utils.build_filter_sql(
        [FilterRule(column='weird"name', op="eq", value="x")], VALID
    )
    assert sql == '"weird""name" = ?'
    assert sql_utils.build_order_sql('weird"name', "asc", VALID) == '"weird""name" ASC'
