"""A close look at one column.

The import quality report answers "is this file sound?" for the file as a whole. This
answers "what is actually in this column?", one column at a time, and it is deliberately
a separate request: the questions worth asking about a column - what its commonest
values are, whether its lengths agree, where its numeric extremes sit - each cost a pass
over four million rows, and nobody wants twenty-two columns' worth of that to look at one.

Every figure in a column's own profile is measured exactly. The one approximation in this
module is the distinct count in `profile_overview`, and it is named `approx_distinct`
rather than presented as a fact: that list exists to pick a column from, an exact
COUNT(DISTINCT) across twenty-two columns of four million rows costs over a second, and
the exact figure is one click away in the column's own profile.

The findings at the end are codes rather than sentences, so the screen can say them in
the reader's own language, and each one is a statement about the data that a person could
check by hand.
"""

import time
from typing import Any, Optional

from app.db.connection import datasets, read_locked
from app.services import sql_utils
from app.services.query import column_kind

# Commonest values shown. Ten is enough to see the shape of a category column without
# turning the panel into the breakdown screen, which exists for exactly that.
TOP_VALUES = 10

# A column at or below this fill rate is worth calling out.
MOSTLY_EMPTY_AT = 5.0

# Above this share of distinct values, a column is an identifier rather than a category -
# grouping by it produces one row per record and tells nobody anything.
IDENTIFIER_AT = 0.95

# A value further than this many interquartile ranges outside the middle is reported as
# an extreme. The conventional multiplier; stated here so it is a decision, not a magic
# number buried in an expression.
OUTLIER_IQR_MULTIPLIER = 1.5


def _pct(part: int, whole: int) -> float:
    return round(part * 100.0 / whole, 2) if whole else 0.0


@read_locked
def profile_column(dataset_id: str, column: str, source: str = "cleaned") -> dict:
    """Everything worth knowing about one column, measured."""
    started = time.perf_counter()

    table = sql_utils.resolve_source_table(dataset_id, source)
    columns = sql_utils.table_columns(dataset_id, table)
    if column not in columns:
        raise ValueError(f"Unknown column: {column}")

    table_sql = sql_utils.quote_ident(table)
    col_sql = sql_utils.quote_ident(column)
    cur = datasets.cursor(dataset_id)

    # One pass for the shape of the column. `filled` counts values that are present *and*
    # not blank, because a column of empty strings is empty however DuckDB stores it.
    present = f"({col_sql} IS NOT NULL AND {col_sql} <> '')"
    total, filled, distinct, min_len, max_len, zero_padded = cur.execute(
        f"""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE {present}),
               COUNT(DISTINCT NULLIF({col_sql}, '')),
               MIN(strlen({col_sql})) FILTER (WHERE {present}),
               MAX(strlen({col_sql})) FILTER (WHERE {present}),
               COUNT(*) FILTER (WHERE {col_sql} LIKE '0%' AND strlen({col_sql}) > 1)
        FROM {table_sql}
        """
    ).fetchone()

    kind = column_kind(dataset_id, source, column)
    missing = total - filled

    top = [
        {"value": v if v is not None else "", "count": n, "pct": _pct(n, total), "blank": v is None}
        for v, n in cur.execute(
            f"""
            SELECT NULLIF({col_sql}, ''), COUNT(*)
            FROM {table_sql}
            GROUP BY 1
            ORDER BY 2 DESC, 1
            LIMIT ?
            """,
            [TOP_VALUES],
        ).fetchall()
    ]

    lengths = [
        {"length": int(length), "count": n, "pct": _pct(n, filled)}
        for length, n in cur.execute(
            f"""
            SELECT strlen({col_sql}), COUNT(*)
            FROM {table_sql}
            WHERE {present}
            GROUP BY 1
            ORDER BY 2 DESC, 1
            LIMIT 8
            """
        ).fetchall()
    ]

    numeric = _numeric(cur, table_sql, col_sql, present) if kind == "number" else None

    return {
        "column": column,
        "kind": kind,
        "source": source,
        "total": total,
        "filled": filled,
        "missing": missing,
        "fill_pct": _pct(filled, total),
        "distinct": distinct,
        "distinct_pct": _pct(distinct, filled),
        "min_length": min_len,
        "max_length": max_len,
        "zero_padded": zero_padded,
        "top_values": top,
        "lengths": lengths,
        "numeric": numeric,
        "findings": _findings(
            total=total, filled=filled, distinct=distinct, min_length=min_len,
            max_length=max_len, zero_padded=zero_padded, numeric=numeric, lengths=lengths,
        ),
        "execution_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def _numeric(cur, table_sql: str, col_sql: str, present: str) -> Optional[dict]:
    """Summary statistics, plus how far the extremes sit outside the middle.

    The column is text like every other one, so every value goes through TRY_CAST and the
    ones that are not numbers become NULL and drop out. That is reported too: a column
    the type sampler called numeric but which holds a thousand non-numeric values is
    exactly the kind of thing this page exists to surface.
    """
    cast = f"TRY_CAST({col_sql} AS DOUBLE)"
    row = cur.execute(
        f"""
        SELECT COUNT({cast}),
               MIN({cast}), MAX({cast}), AVG({cast}),
               QUANTILE_CONT({cast}, 0.25), QUANTILE_CONT({cast}, 0.5),
               QUANTILE_CONT({cast}, 0.75)
        FROM {table_sql} WHERE {present}
        """
    ).fetchone()
    numeric_count, lo, hi, avg, q1, median, q3 = row
    if not numeric_count or lo is None:
        return None

    not_numeric = cur.execute(
        f"SELECT COUNT(*) FROM {table_sql} WHERE {present} AND {cast} IS NULL"
    ).fetchone()[0]

    spread = (q3 - q1) if q1 is not None and q3 is not None else 0
    fence_lo = q1 - OUTLIER_IQR_MULTIPLIER * spread if spread else None
    fence_hi = q3 + OUTLIER_IQR_MULTIPLIER * spread if spread else None
    outliers = 0
    if fence_lo is not None:
        outliers = cur.execute(
            f"SELECT COUNT(*) FROM {table_sql} "
            f"WHERE {present} AND ({cast} < ? OR {cast} > ?)",
            [fence_lo, fence_hi],
        ).fetchone()[0]

    return {
        "count": numeric_count,
        "not_numeric": not_numeric,
        "min": lo,
        "max": hi,
        "avg": round(avg, 4) if avg is not None else None,
        "q1": q1,
        "median": median,
        "q3": q3,
        "outlier_low": fence_lo,
        "outlier_high": fence_hi,
        "outliers": outliers,
    }


def _findings(**f: Any) -> list[dict]:
    """What is worth saying about this column, as codes the screen translates.

    Each is a claim a person could verify. Nothing here is advice - the page reports what
    the column contains and leaves what to do about it to whoever knows the data.
    """
    out: list[dict] = []
    total, filled, distinct = f["total"], f["filled"], f["distinct"]
    missing = total - filled

    if filled == 0:
        out.append({"level": "problem", "code": "entirely_empty"})
        return out

    fill_pct = _pct(filled, total)
    if fill_pct <= MOSTLY_EMPTY_AT:
        out.append({"level": "problem", "code": "mostly_empty", "pct": fill_pct, "missing": missing})
    elif missing:
        out.append({"level": "note", "code": "has_missing", "count": missing, "pct": _pct(missing, total)})

    if distinct == 1:
        out.append({"level": "note", "code": "single_value"})
    elif distinct >= filled * IDENTIFIER_AT:
        # grouping by this produces one row per record; the breakdown screen will refuse
        out.append({"level": "note", "code": "identifier_like", "distinct": distinct})

    if f["zero_padded"]:
        out.append({"level": "note", "code": "zero_padded", "count": f["zero_padded"]})

    if f["min_length"] is not None and f["min_length"] != f["max_length"]:
        # a dominant length with a long tail is the shape of a format that slipped
        dominant = f["lengths"][0] if f["lengths"] else None
        if dominant and dominant["pct"] >= 90 and len(f["lengths"]) > 1:
            out.append(
                {
                    "level": "note",
                    "code": "mixed_lengths",
                    "length": dominant["length"],
                    "pct": dominant["pct"],
                }
            )

    numeric = f["numeric"]
    if numeric:
        if numeric["not_numeric"]:
            out.append(
                {"level": "problem", "code": "not_numeric_values", "count": numeric["not_numeric"]}
            )
        if numeric["outliers"]:
            out.append(
                {
                    "level": "note",
                    "code": "outliers",
                    "count": numeric["outliers"],
                    "low": numeric["outlier_low"],
                    "high": numeric["outlier_high"],
                }
            )
    return out


@read_locked
def profile_overview(dataset_id: str, source: str = "cleaned") -> dict:
    """Every column with just enough to choose which one to look at properly.

    One aggregate query over the whole table rather than one per column, because this is
    the list the page opens on and it must not cost twenty-two passes.
    """
    started = time.perf_counter()
    table = sql_utils.resolve_source_table(dataset_id, source)
    columns = sql_utils.table_columns(dataset_id, table)
    if not columns:
        return {"source": source, "total": 0, "columns": [], "execution_ms": 0.0}

    table_sql = sql_utils.quote_ident(table)
    cur = datasets.cursor(dataset_id)

    # Fill counts are exact - they are the number the page is mostly read for, and the
    # cheap half of the query. Distinct counts are approximate here and only here: an
    # exact COUNT(DISTINCT) on twenty-two columns of four million rows costs over a
    # second, and this list exists to choose a column from, not to be quoted. The exact
    # figure is one click away in that column's own profile, and the field is named so
    # nobody mistakes which one they are looking at.
    selects = []
    for c in columns:
        col = sql_utils.quote_ident(c)
        present = f"({col} IS NOT NULL AND {col} <> '')"
        selects.append(f"COUNT(*) FILTER (WHERE {present})")
        selects.append(f"approx_count_distinct(NULLIF({col}, ''))")
    row = cur.execute(
        f"SELECT COUNT(*), {', '.join(selects)} FROM {table_sql}"
    ).fetchone()

    total = row[0]
    out = []
    for i, name in enumerate(columns):
        filled, approx_distinct = row[1 + i * 2], row[2 + i * 2]
        out.append(
            {
                "name": name,
                "filled": filled,
                "missing": total - filled,
                "fill_pct": _pct(filled, total),
                "approx_distinct": approx_distinct,
            }
        )
    return {
        "source": source,
        "total": total,
        "columns": out,
        "execution_ms": round((time.perf_counter() - started) * 1000, 1),
    }
