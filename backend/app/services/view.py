"""What "the rows on screen" means, said once.

Every question the screen asks about the data it is showing - the grid's page, the value
list under a column header, the grouped view, the statistics, "export the current view" -
has to be asked about the same rows, or its answers describe a table nobody is looking at.
Qusay found the first case of that: 125,375 Kia Picantos on screen, and the engine list
beside them counting all 4.1 million vehicles.

The fix then was to the list. The reason it could happen at all was here: the grid, the
statistics and the export each built their own WHERE clause from the same inputs, and when
"only the latest batch" was added it was added to one of the three. With the toggle on, the
grid showed 400 rows while the colour list beside it counted 30,300 and "export the current
view" wrote 30,300 rows to a file. So there is now one builder, and every consumer asks it.
"""

from typing import Optional

from app.db import catalog
from app.services import arrivals, row_identity, sql_utils


def where(
    dataset_id: str,
    columns: list[str],
    *,
    search: Optional[str] = None,
    search_columns: Optional[list[str]] = None,
    search_alternatives: Optional[list[str]] = None,
    filters=None,
    only_recent: bool = False,
) -> tuple[str, list]:
    """The WHERE fragment for a view (without the keyword, empty when unconstrained),
    and its parameters in matching order."""
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

    if only_recent:
        clauses.append(_recent(dataset_id, columns))

    return " AND ".join(f"({c})" for c in clauses), params


def _recent(dataset_id: str, columns: list[str]) -> str:
    """Only the rows a recent batch brought, as a condition on the table being read.

    "Nothing is known to have arrived" is answered FALSE rather than left out: without
    arrivals, without a key, or on a table that no longer carries the key's columns - a
    cleaned copy that dropped them - the honest answer to "which of these arrived
    recently" is none that can be shown, not all of them.
    """
    key_cols = row_identity.key_columns(catalog.get_dataset(dataset_id) or {})
    if not key_cols or not set(key_cols) <= set(columns):
        return "FALSE"
    return arrivals.recent_filter_sql(dataset_id, key_cols) or "FALSE"
