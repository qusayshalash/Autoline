"""What makes a row *that* row.

Nothing in an imported table answers this. Every column is VARCHAR, there is no primary
key, and DuckDB's `rowid` is a physical position rather than an identity - it changes
under the `CREATE TABLE AS` that both the import (ingestion.py) and every cleaning run
perform. A feature that corrects one record, or that recognises a record arriving again
in a later batch, needs an answer that survives those rebuilds.

The answer is a *business* key: one or more columns of the data itself, named by an
administrator and checked here before it is accepted. A plate number identifies a
vehicle whatever the table does; row 412,905 identifies nothing.

Checked, not assumed. The registry this was built for contains byte-identical duplicate
rows - the cleaning screen exists partly to remove them - so a column that looks like an
identifier may not be one. `validate` runs the count and says how many records share a
key rather than reporting a bare failure, because the number is what tells the reader
whether to add another column to the key or to dedupe first.
"""

import json
from typing import Optional

from app.db.connection import datasets
from app.services import sql_utils

# Enough to combine a few natural columns, few enough that an accidental "key" of every
# column in the file is refused rather than silently accepted as trivially unique.
MAX_KEY_COLUMNS = 4


class KeyProblem(ValueError):
    """A key that cannot be used, carrying the numbers that say why.

    The code travels to the interface, which has the sentence in the reader's language;
    the message is the English fallback and what a log shows.
    """

    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def key_columns(dataset: dict) -> list[str]:
    """The configured key, or an empty list when none has been set.

    An empty list is the honest state for every dataset imported before this existed:
    nothing has been said about what identifies a record, so callers must degrade
    rather than guess.
    """
    raw = dataset.get("key_columns_json")
    if not raw:
        return []
    if isinstance(raw, list):
        return list(raw)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return list(value) if isinstance(value, list) else []


def key_expression(columns: list[str]) -> str:
    """SQL producing one comparable value from the key columns.

    A separator that cannot appear inside a field would be ideal and does not exist -
    any byte is legal in a CSV value. Unit separator (U+001F) is used because it is not
    text anyone types, and the alternative of concatenating without one is worse: keys
    ("ab", "c") and ("a", "bc") would collide, which is a wrong answer rather than an
    unlikely one.

    NULL is mapped to the empty string so a key column that is blank in one row and NULL
    in another does not produce two identities for what the file shows as one value.
    """
    parts = [f"COALESCE({sql_utils.quote_ident(c)}, '')" for c in columns]
    return " || chr(31) || ".join(parts)


def validate(dataset_id: str, columns: list[str], table: str = "raw_data") -> dict:
    """Checks that these columns identify a record, and says what it found.

    Returns the counts even on success: "4,103,522 records, all distinct" is what makes
    the administrator confident rather than merely unblocked.
    """
    if not columns:
        raise KeyProblem("key_empty", "Choose at least one column")
    if len(columns) > MAX_KEY_COLUMNS:
        raise KeyProblem(
            "key_max_columns",
            f"A key may use at most {MAX_KEY_COLUMNS} columns",
            maximum=MAX_KEY_COLUMNS,
        )
    if len(set(columns)) != len(columns):
        raise KeyProblem("key_repeated", "The same column is listed twice")

    available = sql_utils.table_columns(dataset_id, table)
    unknown = [c for c in columns if c not in set(available)]
    if unknown:
        raise KeyProblem(
            "key_unknown_column",
            f"No such column: {', '.join(unknown)}",
            columns=unknown,
        )

    expression = key_expression(columns)
    # Blank means every key column is empty, not any of them: a key of (plate, year)
    # where the year is missing still identifies the row by its plate. Only a row with
    # nothing in any of them has no identity at all.
    all_blank = " AND ".join(
        f"COALESCE({sql_utils.quote_ident(c)}, '') = ''" for c in columns
    )
    cur = datasets.cursor(dataset_id)
    total, distinct, blank = cur.execute(
        f"""
        SELECT COUNT(*),
               COUNT(DISTINCT {expression}),
               COUNT(*) FILTER (WHERE {all_blank})
        FROM {sql_utils.quote_ident(table)}
        """
    ).fetchone()

    return {
        "columns": columns,
        "total_rows": total,
        "distinct_keys": distinct,
        "duplicate_rows": total - distinct,
        "blank_keys": blank,
        "unique": total == distinct and blank == 0,
    }


def require_unique(dataset_id: str, columns: list[str], table: str = "raw_data") -> dict:
    """validate(), refusing anything that cannot identify a record.

    A blank key is rejected separately from a duplicated one because the remedies
    differ: duplicates want another column or a dedupe, blanks want a different column
    entirely - whatever is missing from those rows is missing from the source.
    """
    result = validate(dataset_id, columns, table)
    if result["blank_keys"]:
        raise KeyProblem(
            "key_blank",
            f"{result['blank_keys']} rows have no value in the key columns",
            **result,
        )
    if not result["unique"]:
        raise KeyProblem(
            "key_not_unique",
            f"{result['duplicate_rows']} rows share a key with another row",
            **result,
        )
    return result


def row_key_values(dataset: dict, row: dict) -> Optional[str]:
    """The key of a row already in hand, in the same form key_expression produces."""
    columns = key_columns(dataset)
    if not columns:
        return None
    return "\x1f".join(str(row.get(c) or "") for c in columns)
