"""Safe dynamic SQL building shared by cleaning/query/export.

Column names are always validated against a whitelist fetched from the table itself
(DESCRIBE) before being interpolated into SQL text (quoted identifiers). Values are
never interpolated - they always travel as bound parameters.
"""

from typing import Any

from app.db.connection import datasets
from app.models.schemas import FilterRule

_NUMERIC_OPS = {"gt", "gte", "lt", "lte"}

# The pattern the three text operators wrap the user's value in.
_LIKE_PATTERNS = {
    "contains": "%{}%",
    "starts_with": "{}%",
    "ends_with": "%{}",
}

# Escape character for LIKE patterns. Without it a value containing % or _ would be read
# as a wildcard and quietly match more than the user asked for.
_LIKE_ESCAPE = "\\"


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def escape_like(value: str) -> str:
    """Makes a user-typed value literal inside a LIKE pattern."""
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def table_columns(dataset_id: str, table: str) -> list[str]:
    cur = datasets.cursor(dataset_id)
    return [r[0] for r in cur.execute(f"DESCRIBE {quote_ident(table)}").fetchall()]


def table_exists(dataset_id: str, table: str) -> bool:
    cur = datasets.cursor(dataset_id)
    row = cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0] > 0)


def resolve_source_table(dataset_id: str, source: str) -> str:
    if source == "cleaned" and table_exists(dataset_id, "cleaned_data"):
        return "cleaned_data"
    return "raw_data"


def validate_columns(columns: list[str], valid: set[str]) -> None:
    invalid = [c for c in columns if c not in valid]
    if invalid:
        raise ValueError(f"Unknown column(s): {', '.join(invalid)}")


def build_filter_sql(filters: list[FilterRule], valid_columns: set[str]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for f in filters:
        if f.column not in valid_columns:
            raise ValueError(f"Unknown column: {f.column}")
        col = quote_ident(f.column)
        if f.op == "is_null":
            clauses.append(f"({col} IS NULL OR {col} = '')")
        elif f.op == "not_null":
            clauses.append(f"({col} IS NOT NULL AND {col} != '')")
        elif f.op in _LIKE_PATTERNS:
            # starts_with matters on this data: the manufacturer column pairs a maker
            # with its country, and "טורקיה" (Turkey) ends in the same three letters as
            # "קיה" (Kia) - so `contains` on Kia also returns Toyota Turkey.
            clauses.append(f"{col} ILIKE ? ESCAPE '{_LIKE_ESCAPE}'")
            params.append(_LIKE_PATTERNS[f.op].format(escape_like(str(f.value or ""))))
        elif f.op in _NUMERIC_OPS:
            op_sql = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[f.op]
            clauses.append(f"TRY_CAST({col} AS DOUBLE) {op_sql} TRY_CAST(? AS DOUBLE)")
            params.append(f.value)
        elif f.op == "eq":
            clauses.append(f"{col} = ?")
            params.append(f.value)
        elif f.op == "neq":
            clauses.append(f"{col} != ?")
            params.append(f.value)
        elif f.op == "in":
            values = f.values or []
            if not values:
                continue  # no values selected - contributes no constraint
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(values)
        else:
            raise ValueError(f"Unsupported filter operator: {f.op}")
    return (" AND ".join(clauses), params)


def build_search_sql(search: str, columns: list[str]) -> tuple[str, list[Any]]:
    """Free-text search: does any column of this row contain the text?

    Expressed as one comparison per column rather than one comparison against all of
    them joined together. The joined form - `concat_ws(' ', a, b, ...) ILIKE ?` - reads
    more neatly and is far slower, because the concatenated string has to be built for
    every row before anything can be ruled out. On the 4.1M-row registry that cost a full
    second per search whatever was typed; per column, an OR chain stops at the first
    column that matches and the same search returns in a fraction of it.

    It is also more accurate. Joining the columns puts the end of one value next to the
    start of the next, so a search could match across a boundary that does not exist in
    the data - text that spans two unrelated fields and appears nowhere in either.

    The term is escaped, so a user searching for a literal `%` or `_` gets rows
    containing that character rather than every row in the file.
    """
    if not columns:
        return "FALSE", []
    pattern = f"%{escape_like(search)}%"
    clause = " OR ".join(
        f"{quote_ident(c)} ILIKE ? ESCAPE '{_LIKE_ESCAPE}'" for c in columns
    )
    return f"({clause})", [pattern] * len(columns)


def build_order_sql(sort_by: str, sort_dir: str, valid_columns: set[str]) -> str:
    if sort_by not in valid_columns:
        raise ValueError(f"Unknown column: {sort_by}")
    direction = "DESC" if sort_dir == "desc" else "ASC"
    return f"{quote_ident(sort_by)} {direction}"
