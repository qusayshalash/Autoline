import time

from app.config import settings
from app.db.connection import datasets, read_locked
from app.models.schemas import (
    ColumnInfo,
    ColumnsOut,
    DataPage,
    DataQuery,
    DistinctValueItem,
    DistinctValuesOut,
    GroupItem,
    GroupPage,
    GroupQuery,
)
from app.services import sql_utils

# Rows sampled when guessing a column's display type. Only affects the T/# icon in the
# grid header, so a cheap head-of-table sample is plenty.
_TYPE_SAMPLE_ROWS = 5000

# A "plain" number: no leading zeros, optional sign and decimals. Zero-padded values like
# "01000000" or "0001" deliberately fail this - they are identifiers, not quantities, and
# the loader stores every column as VARCHAR precisely so they keep their padding.
_PLAIN_NUMBER_RE = r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"

# ISO-ish dates, with the day optional so year-month values ("2025-1") still read as dates.
_DATE_RE = r"^\d{4}[-/](0?[1-9]|1[0-2])([-/](0?[1-9]|[12][0-9]|3[01]))?$"

# A text column with at most this many distinct values is treated as a category, which
# lets the grid render its values as coloured chips instead of plain text.
_MAX_CATEGORY_VALUES = 12


def _build_where(
    search: str | None,
    filters: list,
    columns: list[str],
    search_columns: list[str] | None = None,
) -> tuple[str, list]:
    """Shared WHERE builder for the row, group and count queries.

    Returns the SQL fragment (without the WHERE keyword, empty when unconstrained) and
    the bound parameters in matching order.
    """
    clauses: list[str] = []
    params: list = []

    if search:
        looked_in = sql_utils.resolve_search_columns(search_columns, columns)
        s_sql, s_params = sql_utils.build_search_sql(search, looked_in)
        clauses.append(s_sql)
        params.extend(s_params)

    if filters:
        f_sql, f_params = sql_utils.build_filter_sql(filters, set(columns))
        if f_sql:
            clauses.append(f_sql)
            params.extend(f_params)

    return " AND ".join(f"({c})" for c in clauses), params


@read_locked
def fetch_page(dataset_id: str, q: DataQuery) -> DataPage:
    table = sql_utils.resolve_source_table(dataset_id, q.source)
    columns = sql_utils.table_columns(dataset_id, table)
    valid = set(columns)

    where_sql, params = _build_where(q.search, q.filters, columns, q.search_columns)
    table_sql = sql_utils.quote_ident(table)

    started = time.perf_counter()

    cur = datasets.cursor(dataset_id)
    count_sql = f"SELECT COUNT(*) FROM {table_sql}" + (f" WHERE {where_sql}" if where_sql else "")
    total = cur.execute(count_sql, params).fetchone()[0]

    page_size = min(max(q.page_size, 1), settings.max_page_size)
    page = max(q.page, 1)
    offset = (page - 1) * page_size

    order_sql = ""
    if q.sort_by:
        order_sql = " ORDER BY " + sql_utils.build_order_sql(q.sort_by, q.sort_dir, valid)

    cols_sql = ", ".join(sql_utils.quote_ident(c) for c in columns)
    data_sql = (
        f"SELECT {cols_sql} FROM {table_sql}"
        + (f" WHERE {where_sql}" if where_sql else "")
        + order_sql
        + " LIMIT ? OFFSET ?"
    )
    rows = cur.execute(data_sql, [*params, page_size, offset]).fetchall()

    duration_ms = (time.perf_counter() - started) * 1000

    return DataPage(
        columns=columns,
        rows=[list(r) for r in rows],
        total_rows=total,
        page=page,
        page_size=page_size,
        duration_ms=round(duration_ms, 1),
    )


@read_locked
def fetch_groups(dataset_id: str, q: GroupQuery) -> GroupPage:
    """Group by a single column and return each distinct value with its row count.

    Nesting is handled by the caller rather than here: to drill into a group, call this
    again for the next column with the parent's value added as an equality filter. That
    keeps one simple query behind every level of the tree, and means group counts always
    respect the view's own filters and search.
    """
    table = sql_utils.resolve_source_table(dataset_id, q.source)
    columns = sql_utils.table_columns(dataset_id, table)
    if q.column not in columns:
        raise ValueError(f"Unknown column: {q.column}")

    where_sql, params = _build_where(q.search, q.filters, columns, q.search_columns)
    table_sql = sql_utils.quote_ident(table)
    col_sql = sql_utils.quote_ident(q.column)
    where_clause = f" WHERE {where_sql}" if where_sql else ""

    page_size = min(max(q.page_size, 1), settings.max_page_size)
    page = max(q.page, 1)
    offset = (page - 1) * page_size

    started = time.perf_counter()
    cur = datasets.cursor(dataset_id)

    total_groups = cur.execute(
        f"SELECT COUNT(*) FROM (SELECT 1 FROM {table_sql}{where_clause} GROUP BY {col_sql})",
        params,
    ).fetchone()[0]

    rows = cur.execute(
        f"""
        SELECT {col_sql}, COUNT(*) AS n FROM {table_sql}{where_clause}
        GROUP BY {col_sql}
        ORDER BY n DESC, {col_sql}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()

    duration_ms = (time.perf_counter() - started) * 1000

    return GroupPage(
        column=q.column,
        groups=[GroupItem(value=r[0], count=r[1]) for r in rows],
        total_groups=total_groups,
        page=page,
        page_size=page_size,
        duration_ms=round(duration_ms, 1),
    )


def _infer_kinds(dataset_id: str, table: str, columns: list[str]) -> dict[str, str]:
    """Sample the head of the table and classify each of `columns`.

    One query regardless of how many columns are asked for, but the cost scales with
    that number (four aggregates each, two of them regex), so callers that need a single
    column should ask for a single column - see `column_kind`.
    """
    if not columns:
        return {}

    selects: list[str] = []
    params: list = []
    for c in columns:
        col = sql_utils.quote_ident(c)
        selects.append(f"COUNT(*) FILTER (WHERE {col} IS NOT NULL AND {col} != '')")
        selects.append(f"COUNT(*) FILTER (WHERE regexp_matches({col}, ?))")
        selects.append(f"COUNT(*) FILTER (WHERE regexp_matches({col}, ?))")
        selects.append(f"COUNT(DISTINCT NULLIF({col}, ''))")
        params.extend([_PLAIN_NUMBER_RE, _DATE_RE])

    sql = (
        f"SELECT {', '.join(selects)} FROM "
        f"(SELECT * FROM {sql_utils.quote_ident(table)} LIMIT {_TYPE_SAMPLE_ROWS})"
    )
    row = datasets.cursor(dataset_id).execute(sql, params).fetchone()

    kinds: dict[str, str] = {}
    for i, name in enumerate(columns):
        non_empty, numeric, datelike, distinct = row[i * 4 : i * 4 + 4]
        if non_empty == 0:
            kind = "text"
        elif datelike == non_empty:
            kind = "date"
        elif numeric == non_empty:
            # a numeric column stays numeric even when it has few distinct values -
            # counts and codes read better as figures than as chips
            kind = "number"
        elif distinct <= _MAX_CATEGORY_VALUES:
            kind = "category"
        else:
            kind = "text"
        kinds[name] = kind
    return kinds


@read_locked
def column_types(dataset_id: str, source: str) -> ColumnsOut:
    """Infer a display type per column by sampling values.

    DuckDB reports every column as VARCHAR here (the loader uses all_varchar so that
    zero-padded IDs survive import), so the stored type carries no information - the
    kind is derived from what the values actually look like.
    """
    table = sql_utils.resolve_source_table(dataset_id, source)
    columns = sql_utils.table_columns(dataset_id, table)
    kinds = _infer_kinds(dataset_id, table, columns)
    return ColumnsOut(columns=[ColumnInfo(name=c, kind=kinds[c]) for c in columns])


def column_kind(dataset_id: str, source: str, column: str) -> str:
    """The inferred kind of one column, without paying for the other twenty-two."""
    table = sql_utils.resolve_source_table(dataset_id, source)
    if column not in sql_utils.table_columns(dataset_id, table):
        raise ValueError(f"Unknown column: {column}")
    return _infer_kinds(dataset_id, table, [column])[column]


@read_locked
def distinct_values(
    dataset_id: str, source: str, column: str, search: str | None, limit: int | None
) -> DistinctValuesOut:
    table = sql_utils.resolve_source_table(dataset_id, source)
    columns = sql_utils.table_columns(dataset_id, table)
    if column not in columns:
        raise ValueError(f"Unknown column: {column}")

    col_sql = sql_utils.quote_ident(column)
    table_sql = sql_utils.quote_ident(table)
    cap = min(max(limit or settings.distinct_values_limit, 1), settings.distinct_values_limit)

    where_sql = f"{col_sql} IS NOT NULL AND {col_sql} != ''"
    params: list = []
    if search:
        where_sql += f" AND {col_sql} ILIKE ?"
        params.append(f"%{search}%")

    cur = datasets.cursor(dataset_id)
    total = cur.execute(
        f"SELECT COUNT(DISTINCT {col_sql}) FROM {table_sql} WHERE {where_sql}", params
    ).fetchone()[0]

    rows = cur.execute(
        f"""
        SELECT {col_sql}, COUNT(*) FROM {table_sql} WHERE {where_sql}
        GROUP BY {col_sql}
        ORDER BY COUNT(*) DESC, {col_sql}
        LIMIT ?
        """,
        [*params, cap],
    ).fetchall()
    values = [DistinctValueItem(value=r[0], count=r[1]) for r in rows]

    return DistinctValuesOut(column=column, values=values, total_distinct=total, truncated=total > len(values))
