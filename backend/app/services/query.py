import time

from app.config import settings
from app.db import catalog
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
from app.services import arrivals, row_identity, sql_utils

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
    search_alternatives: list[str] | None = None,
) -> tuple[str, list]:
    """Shared WHERE builder for the row, group and count queries.

    Returns the SQL fragment (without the WHERE keyword, empty when unconstrained) and
    the bound parameters in matching order.
    """
    clauses: list[str] = []
    params: list = []

    if search:
        looked_in = sql_utils.resolve_search_columns(search_columns, columns)
        s_sql, s_params = sql_utils.build_search_sql(search, looked_in, search_alternatives)
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

    where_sql, params = _build_where(
        q.search, q.filters, columns, q.search_columns, q.search_alternatives
    )

    # "only what arrived recently" is not a statement about a column, so it joins the
    # WHERE here rather than going through the filter builder. It costs nothing when it
    # is not asked for, which is almost always.
    key_cols = row_identity.key_columns(catalog.get_dataset(dataset_id) or {})
    if q.only_recent:
        recent = arrivals.recent_filter_sql(dataset_id, key_cols)
        # No arrivals table and no key both mean the same thing here: nothing is known
        # to have arrived, which is not the same as everything having arrived.
        recent = recent or "FALSE"
        where_sql = f"({where_sql}) AND ({recent})" if where_sql else recent
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
        # The kind lookup runs a query of its own, so the name has to be known to be a
        # real column before it is asked about. Reversed, an unknown name reaches DuckDB
        # here and returns a 500 instead of the 400 build_order_sql raises for it.
        numeric = q.sort_by in valid and sorts_numerically(dataset_id, table, q.sort_by)
        order_sql = " ORDER BY " + sql_utils.build_order_sql(
            q.sort_by, q.sort_dir, valid, numeric=numeric
        )

    cols_sql = ", ".join(sql_utils.quote_ident(c) for c in columns)
    data_sql = (
        f"SELECT {cols_sql} FROM {table_sql}"
        + (f" WHERE {where_sql}" if where_sql else "")
        + order_sql
        + " LIMIT ? OFFSET ?"
    )
    rows = cur.execute(data_sql, [*params, page_size, offset]).fetchall()

    duration_ms = (time.perf_counter() - started) * 1000

    # Asked of the hundred rows in hand rather than joined into the query above: almost
    # no row in a four-million-row table is recent, and every reader would otherwise pay
    # on every page to find that out.
    marks = arrivals.mark_page(dataset_id, key_cols, rows, columns)

    return DataPage(
        columns=columns,
        rows=[list(r) for r in rows],
        total_rows=total,
        page=page,
        page_size=page_size,
        duration_ms=round(duration_ms, 1),
        arrivals=marks,
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

    where_sql, params = _build_where(
        q.search, q.filters, columns, q.search_columns, q.search_alternatives
    )
    table_sql = sql_utils.quote_ident(table)
    col_sql = sql_utils.quote_ident(q.column)

    # The picker's own search box, which asks about this column's values rather than
    # about the rows. It goes through the same builder as any other search, so a typed
    # term reaches a translated value through the dictionary and a literal % stays a
    # character.
    if q.value_search:
        v_sql, v_params = sql_utils.build_search_sql(
            q.value_search, [q.column], q.value_search_alternatives
        )
        where_sql = f"({where_sql}) AND {v_sql}" if where_sql else v_sql
        params = [*params, *v_params]

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


def sorts_numerically(dataset_id: str, table: str, column: str) -> bool:
    """Whether ordering by this column should compare numbers instead of text.

    Deliberately the same classifier the grid labels its columns with, rather than a
    cheaper "does it cast?" test. A column of zero-padded ids casts perfectly well and
    is still not a number - 00000001 is meant to sort as written - and a sort that
    disagreed with the kind shown above it would be the same inconsistency this
    replaced, moved somewhere harder to see.

    It costs a sampling query per sorted request: about 28ms on a 148-column table,
    under 10ms on a narrow one. Worth knowing before adding a second caller, though it
    sits well inside the ~1.8s the same page already spends typing all 148 columns.

    Takes the table rather than the source because both callers have already resolved it.
    """
    return _infer_kinds(dataset_id, table, [column]).get(column) == "number"


@read_locked
def distinct_values(
    dataset_id: str,
    source: str,
    column: str,
    search: str | None,
    limit: int | None,
    search_alternatives: list[str] | None = None,
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
        # The same builder the grid's search uses, so a typed term finds the same values
        # here as it does there - including through the value dictionary - and a literal
        # % or _ is a character rather than a wildcard.
        s_sql, s_params = sql_utils.build_search_sql(search, [column], search_alternatives)
        where_sql += f" AND {s_sql}"
        params.extend(s_params)

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
