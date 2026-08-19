"""Aggregation queries behind the Statistics dashboard.

Everything here answers the same shape of question - "how do the matching rows split
across one column?" - and answers it entirely inside DuckDB. The frontend never receives
rows, only the finished buckets, so a 4M-row file costs the same over the wire as a 4k
one.

Three breakdown modes, chosen from the column's inferred kind:
  value     - GROUP BY the value itself (categories, text, and numbers with few values)
  date      - GROUP BY a truncated year/month/day
  histogram - equal-width buckets across the numeric range

Filters and search reuse the exact builders the data grid uses (`sql_utils`), so a
statistic always describes the same subset the user would see in the table. Values are
bound as parameters throughout; only column names reach the SQL text, and only after
being checked against the table's own column list.
"""

import time
from typing import Any

from app.db.connection import datasets, read_locked
from app.models.schemas import (
    BreakdownItem,
    ColumnSuggestion,
    NumericSummary,
    PivotHeader,
    PivotOut,
    PivotQuery,
    PivotRow,
    StatisticsOut,
    StatisticsQuery,
)
from app.services import sql_utils
from app.services.query import column_kind, column_types

# Buckets returned by default. Anything past the cut is folded into a single "other" row
# so the response stays small and the chart readable no matter how wide the column is
# (degem_nm has 10k distinct values).
_DEFAULT_ITEMS = 50
_HARD_MAX_ITEMS = 200

# Above this many distinct values a numeric column is bucketed into a histogram instead
# of being grouped value by value. Years (31 distinct) stay discrete; mileage does not.
_DISCRETE_NUMBER_LIMIT = 60

_DATE_UNITS = {
    "year": "%Y",
    "month": "%Y-%m",
    "day": "%Y-%m-%d",
}

# Dates arrive as text and this registry is not consistent about precision: tokef_dt
# holds "2026-12-31" while moed_aliya_lakvish holds "2025-1". A plain TRY_CAST turns the
# second form into NULL - which showed up as a chart that was 100% "unspecified" - so
# year-month needs a parser of its own. TRY_CAST already covers full dates with either
# separator and unpadded parts ("2027/1/5"), so only year-month forms are listed here.
#
# Which parsers a column actually needs is decided per column, because an unused one is
# not free: TRY_CAST failing on all 4.1M values costs ~330ms by itself, and stacking
# every parser unconditionally made a year breakdown take 3.5s where one parser takes
# ~150ms.
_DATE_PARSERS = (
    "TRY_CAST({col} AS DATE)",
    "CAST(TRY_STRPTIME({col}, '%Y-%m') AS DATE)",
    "CAST(TRY_STRPTIME({col}, '%Y/%m') AS DATE)",
)

# Block-level sample used to pick those parsers. Cheap (~15ms on 4.1M rows) and spread
# across the whole table rather than its head, so a column whose format changes partway
# through is still described correctly.
_DATE_PROBE_PERCENT = 1

# Rows sampled by suggest_columns when estimating a column's cardinality.
_SUGGEST_SAMPLE = 20000


def _date_parse_expr(cur, table_sql: str, col_sql: str) -> str:
    """An expression parsing this column to DATE, using only the parsers it needs.

    Parsers that match nothing in the sample are left out; if none match - an all-empty
    column, or a sample that came back empty - every parser is kept, so a bad sample
    costs speed rather than correctness.
    """
    selects = ", ".join(f"COUNT({p.format(col=col_sql)})" for p in _DATE_PARSERS)
    counts = cur.execute(
        f"SELECT {selects} FROM (SELECT {col_sql} FROM {table_sql} "
        f"USING SAMPLE {_DATE_PROBE_PERCENT} PERCENT (system, 42))"
    ).fetchone()

    used = [p.format(col=col_sql) for p, n in zip(_DATE_PARSERS, counts) if n]
    if not used:
        used = [p.format(col=col_sql) for p in _DATE_PARSERS]
    return used[0] if len(used) == 1 else f"COALESCE({', '.join(used)})"


def _bucket_expr(column: str, mode: str, granularity: str, date_parse: str = "") -> str:
    """SQL producing the label a row is grouped under, as VARCHAR or NULL.

    NULL is the "unspecified" bucket and is produced deliberately: empty strings are
    folded into it by NULLIF, and a value that no date parser accepts lands there rather
    than failing the query. Dates are stored as text because the loader keeps every
    column VARCHAR so zero-padded identifiers survive import.
    """
    col = sql_utils.quote_ident(column)
    if mode == "date":
        unit = granularity if granularity in _DATE_UNITS else "year"
        return f"strftime(date_trunc('{unit}', {date_parse}), '{_DATE_UNITS[unit]}')"
    return f"NULLIF(TRIM({col}), '')"


def _build_where(q: StatisticsQuery | PivotQuery, columns: list[str]) -> tuple[str, list[Any]]:
    """Shared by both breakdown shapes - they carry the same `search` and `filters`, so a
    cross-tab always describes the same subset a one-dimensional breakdown would."""
    clauses: list[str] = []
    params: list[Any] = []
    if q.search:
        s_sql, s_params = sql_utils.build_search_sql(q.search, columns)
        clauses.append(s_sql)
        params.extend(s_params)
    if q.filters:
        f_sql, f_params = sql_utils.build_filter_sql(q.filters, set(columns))
        if f_sql:
            clauses.append(f_sql)
            params.extend(f_params)
    return " AND ".join(f"({c})" for c in clauses), params


@read_locked
def compute(dataset_id: str, q: StatisticsQuery) -> StatisticsOut:
    # Timed from the very first query: the reported figure is what the request actually
    # cost, including the type sampling, not just the aggregate at the end of it.
    started = time.perf_counter()

    table = sql_utils.resolve_source_table(dataset_id, q.source)
    columns = sql_utils.table_columns(dataset_id, table)
    if q.group_by not in columns:
        raise ValueError(f"Unknown column: {q.group_by}")

    kind = column_kind(dataset_id, q.source, q.group_by)

    where_sql, params = _build_where(q, columns)
    where_clause = f" WHERE {where_sql}" if where_sql else ""
    table_sql = sql_utils.quote_ident(table)
    col_sql = sql_utils.quote_ident(q.group_by)
    limit = min(max(q.limit or _DEFAULT_ITEMS, 1), _HARD_MAX_ITEMS)

    cur = datasets.cursor(dataset_id)

    total = cur.execute(f"SELECT COUNT(*) FROM {table_sql}{where_clause}", params).fetchone()[0]
    grand_total = cur.execute(f"SELECT COUNT(*) FROM {table_sql}").fetchone()[0]

    if total == 0:
        return StatisticsOut(
            group_by=q.group_by,
            kind=kind,
            mode="value",
            total=0,
            grand_total=grand_total,
            items=[],
            distinct_values=0,
            truncated=False,
            execution_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    mode = _mode_for(cur, table_sql, col_sql, kind, where_clause, params)
    numeric = None

    if mode == "histogram":
        items, distinct, truncated, numeric = _histogram(
            cur, table_sql, col_sql, where_clause, params, total, q.bins
        )
    else:
        date_parse = _date_parse_expr(cur, table_sql, col_sql) if mode == "date" else ""
        expr = _bucket_expr(q.group_by, mode, q.granularity, date_parse)
        items, distinct, truncated = _grouped(
            cur, table_sql, expr, where_clause, params, total, limit, q.sort
        )
        if kind == "number":
            numeric = _numeric_summary(cur, table_sql, col_sql, where_clause, params)

    return StatisticsOut(
        group_by=q.group_by,
        kind=kind,
        mode=mode,
        total=total,
        grand_total=grand_total,
        items=items,
        distinct_values=distinct,
        truncated=truncated,
        numeric=numeric,
        execution_ms=round((time.perf_counter() - started) * 1000, 1),
    )


def _mode_for(cur, table_sql, col_sql, kind, where_clause, params) -> str:
    if kind == "date":
        return "date"
    if kind != "number":
        return "value"
    distinct = cur.execute(
        f"SELECT COUNT(DISTINCT {col_sql}) FROM {table_sql}{where_clause}", params
    ).fetchone()[0]
    return "value" if distinct <= _DISCRETE_NUMBER_LIMIT else "histogram"


def _grouped(
    cur,
    table_sql: str,
    expr: str,
    where_clause: str,
    params: list,
    total: int,
    limit: int,
    sort: str,
) -> tuple[list[BreakdownItem], int, bool]:
    # "value" ordering matters for years and months, where chronological beats popular.
    order_sql = "bucket NULLS LAST" if sort == "value" else "n DESC, bucket"

    # One pass, not two. The distinct count rides along as an uncorrelated subquery over
    # the same CTE, so the bucket expression is evaluated once - which matters most for
    # date columns, where parsing 4.1M strings twice was costing whole seconds.
    #
    # The count includes the NULL bucket. It has to: that bucket is displayed as a row
    # like any other, and the screen reads "showing N of M values" - so excluding it
    # would have the page show a bucket it claims does not exist. The cross-tab counts
    # its axes the same way (see distinct_rows_with_null).
    rows = cur.execute(
        f"""
        WITH buckets AS (
            SELECT {expr} AS bucket, COUNT(*) AS n
            FROM {table_sql}{where_clause}
            GROUP BY bucket
        )
        SELECT bucket, n, (SELECT COUNT(*) FROM buckets)
        FROM buckets
        ORDER BY {order_sql}
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()

    distinct = rows[0][2] if rows else 0
    items = [
        BreakdownItem(
            value=r[0] if r[0] is not None else "",
            count=r[1],
            percentage=round(r[1] * 100.0 / total, 2),
            unspecified=r[0] is None,
        )
        for r in rows
    ]

    # Everything past the cut becomes one "other" bucket so the percentages still add up
    # to 100 and the user can see how much was folded away.
    shown = sum(i.count for i in items)
    truncated = shown < total
    if truncated:
        rest = total - shown
        items.append(
            BreakdownItem(
                value="",
                count=rest,
                percentage=round(rest * 100.0 / total, 2),
                other=True,
            )
        )
    return items, distinct, truncated


def _numeric_summary(cur, table_sql: str, col_sql: str, where_clause: str, params: list):
    row = cur.execute(
        f"""
        SELECT COUNT(v), MIN(v), MAX(v), AVG(v), MEDIAN(v)
        FROM (SELECT TRY_CAST({col_sql} AS DOUBLE) AS v FROM {table_sql}{where_clause})
        WHERE v IS NOT NULL
        """,
        params,
    ).fetchone()
    if not row or not row[0]:
        return None
    count, lo, hi, avg, med = row
    return NumericSummary(
        count=count,
        min=float(lo),
        max=float(hi),
        avg=float(avg),
        median=float(med) if med is not None else None,
    )


def _histogram(
    cur, table_sql: str, col_sql: str, where_clause: str, params: list, total: int, bins: int
) -> tuple[list[BreakdownItem], int, bool, NumericSummary | None]:
    """Equal-width buckets across the observed range.

    Rows whose value doesn't parse as a number are not silently dropped - they are
    reported as the unspecified bucket, so the percentages describe every matching row
    rather than only the numeric ones.
    """
    bins = min(max(bins or 20, 2), 100)
    inner = f"SELECT TRY_CAST({col_sql} AS DOUBLE) AS v FROM {table_sql}{where_clause}"

    numeric_count, lo, hi, avg, med = cur.execute(
        f"SELECT COUNT(v), MIN(v), MAX(v), AVG(v), MEDIAN(v) FROM ({inner})", params
    ).fetchone()
    non_numeric = total - numeric_count

    if not numeric_count:
        return (
            [BreakdownItem(value="", count=total, percentage=100.0, unspecified=True)],
            0,
            False,
            None,
        )

    summary = NumericSummary(
        count=numeric_count,
        min=float(lo),
        max=float(hi),
        avg=float(avg),
        median=float(med) if med is not None else None,
    )

    items: list[BreakdownItem] = []
    if hi == lo:  # a single value - one bucket, no arithmetic needed
        items.append(
            BreakdownItem(
                value=_fmt_range(lo, hi),
                count=numeric_count,
                percentage=round(numeric_count * 100.0 / total, 2),
                bucket_min=float(lo),
                bucket_max=float(hi),
            )
        )
    else:
        width = (hi - lo) / bins
        # Parameter order follows the SQL *text*: the three bucket parameters appear in
        # the SELECT list, ahead of the filter parameters carried by the inner query.
        rows = cur.execute(
            f"""
            SELECT LEAST(CAST(FLOOR((v - ?) / ?) AS INTEGER), ?) AS b, COUNT(*)
            FROM ({inner}) WHERE v IS NOT NULL
            GROUP BY b ORDER BY b
            """,
            [lo, width, bins - 1, *params],
        ).fetchall()
        for b, n in rows:
            start, end = lo + b * width, lo + (b + 1) * width
            items.append(
                BreakdownItem(
                    value=_fmt_range(start, end),
                    count=n,
                    percentage=round(n * 100.0 / total, 2),
                    bucket_min=start,
                    bucket_max=end,
                )
            )

    if non_numeric:
        items.append(
            BreakdownItem(
                value="",
                count=non_numeric,
                percentage=round(non_numeric * 100.0 / total, 2),
                unspecified=True,
            )
        )

    return items, numeric_count, False, summary


def _fmt_range(start: float, end: float) -> str:
    def one(v: float) -> str:
        return str(int(v)) if float(v).is_integer() else f"{v:.2f}"

    return one(start) if start == end else f"{one(start)} - {one(end)}"


@read_locked
def compute_pivot(dataset_id: str, q: PivotQuery) -> PivotOut:
    """A cross-tab: how the matching rows split across two columns at once.

    The obvious implementation - group by both columns and send the grid - falls over on
    real data: model name x colour is 10,091 x 100, a million cells nobody will read.
    So the axes are cut to their largest members and everything outside is folded into an
    "other" band on each edge.

    Those bands are computed, not sampled. Three queries give the full row totals, the
    full column totals, and the cells inside the cut; the outside is then exact
    arithmetic - a row's other-cell is its true total minus the cells shown, and the
    corner follows by inclusion-exclusion. Nothing is estimated, and every margin still
    adds up to the real total.
    """
    started = time.perf_counter()

    table = sql_utils.resolve_source_table(dataset_id, q.source)
    columns = sql_utils.table_columns(dataset_id, table)
    for name in (q.row_column, q.column_column):
        if name not in columns:
            raise ValueError(f"Unknown column: {name}")
    if q.row_column == q.column_column:
        raise ValueError("Pick two different columns")

    row_kind = column_kind(dataset_id, q.source, q.row_column)
    col_kind = column_kind(dataset_id, q.source, q.column_column)

    where_sql, params = _build_where(q, columns)
    where_clause = f" WHERE {where_sql}" if where_sql else ""
    table_sql = sql_utils.quote_ident(table)

    row_expr = _bucket_expr(
        q.row_column,
        "date" if row_kind == "date" else "value",
        q.row_granularity,
        _date_parse_expr(datasets.cursor(dataset_id), table_sql, sql_utils.quote_ident(q.row_column))
        if row_kind == "date"
        else "",
    )
    col_expr = _bucket_expr(
        q.column_column,
        "date" if col_kind == "date" else "value",
        q.column_granularity,
        _date_parse_expr(
            datasets.cursor(dataset_id), table_sql, sql_utils.quote_ident(q.column_column)
        )
        if col_kind == "date"
        else "",
    )

    cur = datasets.cursor(dataset_id)
    base = f"SELECT {row_expr} AS r, {col_expr} AS c FROM {table_sql}{where_clause}"

    total = cur.execute(f"SELECT COUNT(*) FROM ({base})", params).fetchone()[0]
    grand_total = cur.execute(f"SELECT COUNT(*) FROM {table_sql}").fetchone()[0]

    if total == 0:
        return PivotOut(
            row_column=q.row_column,
            column_column=q.column_column,
            row_kind=row_kind,
            column_kind=col_kind,
            columns=[],
            rows=[],
            total=0,
            grand_total=grand_total,
            distinct_rows=0,
            distinct_columns=0,
            rows_truncated=False,
            columns_truncated=False,
            execution_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    row_headers, distinct_rows = _axis(cur, base, "r", params, q.row_limit)
    col_headers, distinct_cols = _axis(cur, base, "c", params, q.column_limit)

    # cells inside the cut only - joined on IS NOT DISTINCT FROM so the unspecified
    # bucket (a real NULL) matches like any other value
    cells = cur.execute(
        f"""
        WITH b AS ({base}),
             tr AS (SELECT r, COUNT(*) AS n FROM b GROUP BY 1 ORDER BY n DESC, r LIMIT ?),
             tc AS (SELECT c, COUNT(*) AS n FROM b GROUP BY 1 ORDER BY n DESC, c LIMIT ?)
        SELECT b.r, b.c, COUNT(*)
        FROM b
        JOIN tr ON b.r IS NOT DISTINCT FROM tr.r
        JOIN tc ON b.c IS NOT DISTINCT FROM tc.c
        GROUP BY 1, 2
        """,
        [*params, q.row_limit, q.column_limit],
    ).fetchall()

    grid: dict[tuple, int] = {(r, c): n for r, c, n in cells}
    # The axis sizes already count the unspecified bucket, so they answer the truncation
    # question directly - no second pair of queries needed.
    rows_truncated = len(row_headers) < distinct_rows
    cols_truncated = len(col_headers) < distinct_cols

    return _assemble(
        q,
        row_kind,
        col_kind,
        row_headers,
        col_headers,
        grid,
        total,
        grand_total,
        distinct_rows,
        distinct_cols,
        rows_truncated,
        cols_truncated,
        started,
    )


def _axis(cur, base: str, field: str, params: list, limit: int) -> tuple[list[tuple], int]:
    """The largest `limit` members of one axis, with their true totals and the size of
    the axis they were drawn from."""
    rows = cur.execute(
        f"SELECT {field}, COUNT(*) AS n FROM ({base}) GROUP BY 1 ORDER BY n DESC, {field} LIMIT ?",
        [*params, limit],
    ).fetchall()
    return rows, distinct_rows_with_null(cur, base, field, params)


def distinct_rows_with_null(cur, base: str, field: str, params: list) -> int:
    """The number of members on an axis, counting the unspecified bucket as one of them.

    COUNT(DISTINCT) would skip it, and the blank bucket is a member like any other: it
    occupies a row or a column on screen, and the header reports the axis size next to
    it. Undercounting here had two visible effects - an axis fully inside the cut was
    reported as truncated whenever it contained blanks, and the shape note claimed one
    fewer category than the matrix displayed.
    """
    return cur.execute(
        f"SELECT COUNT(*) FROM (SELECT {field} FROM ({base}) GROUP BY 1)", params
    ).fetchone()[0]


def _assemble(
    q: PivotQuery,
    row_kind: str,
    col_kind: str,
    row_headers: list[tuple],
    col_headers: list[tuple],
    grid: dict,
    total: int,
    grand_total: int,
    distinct_rows: int,
    distinct_cols: int,
    rows_truncated: bool,
    cols_truncated: bool,
    started: float,
) -> PivotOut:
    def header(value, count: int) -> PivotHeader:
        return PivotHeader(
            value=value if value is not None else "", total=count, unspecified=value is None
        )

    columns = [header(v, n) for v, n in col_headers]
    shown_col_total = sum(n for _, n in col_headers)
    shown_row_total = sum(n for _, n in row_headers)

    rows: list[PivotRow] = []
    for value, row_total in row_headers:
        cells = [grid.get((value, cv), 0) for cv, _ in col_headers]
        if cols_truncated:
            # everything this row has outside the shown columns
            cells.append(row_total - sum(cells))
        rows.append(PivotRow(header=header(value, row_total), cells=cells))

    if cols_truncated:
        columns.append(PivotHeader(value="", total=total - shown_col_total, other=True))

    if rows_truncated:
        # the other-row is each column's true total minus what the shown rows hold, and
        # the corner closes by inclusion-exclusion
        other_cells = [
            col_total - sum(grid.get((rv, cv), 0) for rv, _ in row_headers)
            for cv, col_total in col_headers
        ]
        if cols_truncated:
            other_cells.append(
                total - shown_row_total - shown_col_total + sum(grid.values())
            )
        rows.append(
            PivotRow(
                header=PivotHeader(value="", total=total - shown_row_total, other=True),
                cells=other_cells,
            )
        )

    return PivotOut(
        row_column=q.row_column,
        column_column=q.column_column,
        row_kind=row_kind,
        column_kind=col_kind,
        columns=columns,
        rows=rows,
        total=total,
        grand_total=grand_total,
        distinct_rows=distinct_rows,
        distinct_columns=distinct_cols,
        rows_truncated=rows_truncated,
        columns_truncated=cols_truncated,
        execution_ms=round((time.perf_counter() - started) * 1000, 1),
    )


@read_locked
def suggest_columns(dataset_id: str, source: str) -> list[ColumnSuggestion]:
    """Columns worth offering as a breakdown, with an estimate of their cardinality.

    A column with as many distinct values as rows (a chassis number) makes a useless
    chart, so the frontend needs the cardinality to rank columns and to warn. Counting
    DISTINCT on every column of a 4M-row table is expensive, so this samples the head of
    the table - enough to tell "a handful of categories" from "millions of identifiers".
    """
    table = sql_utils.resolve_source_table(dataset_id, source)
    columns = sql_utils.table_columns(dataset_id, table)
    if not columns:
        return []

    kinds = {c.name: c.kind for c in column_types(dataset_id, source).columns}
    selects = ", ".join(
        f"COUNT(DISTINCT NULLIF(TRIM({sql_utils.quote_ident(c)}), ''))" for c in columns
    )
    row = (
        datasets.cursor(dataset_id)
        .execute(
            f"SELECT {selects} FROM "
            f"(SELECT * FROM {sql_utils.quote_ident(table)} LIMIT {_SUGGEST_SAMPLE})"
        )
        .fetchone()
    )

    return [
        ColumnSuggestion(
            name=name,
            kind=kinds.get(name, "text"),
            approx_distinct=row[i],
            sampled_rows=_SUGGEST_SAMPLE,
        )
        for i, name in enumerate(columns)
    ]
