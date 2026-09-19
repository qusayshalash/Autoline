"""Adding a later batch of the same data to a dataset that already exists.

A registry arrives in instalments. The second file is the same shape as the first and
means the same thing, and what the reader wants is one dataset containing both - not two
datasets they have to remember to search separately.

Two things make this more than an INSERT.

**A record that arrives twice.** The later batch is usually a fresher statement about
some of the same records, so a plate already in the table should end up with the new
row's values rather than sitting beside a second copy of itself. That needs a key, and
the dataset only has one if an administrator has named it (see row_identity). Without a
key this still works - it just adds, and says so.

**Re-import must not lose the batches.** `raw_data` is rebuilt from the uploaded file by
`CREATE TABLE AS`, so an appended batch that lived only in the table would vanish the
next time anyone re-ran the import, silently and completely. So each batch is kept on
disk beside the original upload, normalised into the dataset's own column order, and
replayed after any rebuild. The files on disk remain the whole truth about the dataset,
which is the property the rest of the system is built on.

The stored batch is written without a header and in the dataset's column order, so
replaying it needs no per-batch metadata: one shape, positional, always.
"""

import csv
import json
import re
from pathlib import Path
from typing import Callable, Optional

from app.db import catalog
from app.db.connection import datasets
from app.services import corrections, ingestion, row_identity, sql_utils

BATCH_PREFIX = "batch-"
_BATCH_NAME = re.compile(r"^batch-(\d{4})\.csv$")

# The delimiter every stored batch is written with, whatever the source file used.
BATCH_DELIMITER = ","


class AppendProblem(ValueError):
    """A batch that cannot be appended, with the reason in a translatable code."""

    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


# ---- the files on disk ------------------------------------------------------------

def batch_files(dataset_id: str) -> list[Path]:
    """Every stored batch, in the order it was appended."""
    directory = ingestion.dataset_upload_dir(dataset_id)
    return sorted(p for p in directory.glob("batch-*.csv") if _BATCH_NAME.match(p.name))


def next_batch_path(dataset_id: str) -> Path:
    existing = batch_files(dataset_id)
    number = 1 + max((int(_BATCH_NAME.match(p.name).group(1)) for p in existing), default=0)
    return ingestion.dataset_upload_dir(dataset_id) / f"{BATCH_PREFIX}{number:04d}.csv"


# ---- checking the incoming file ---------------------------------------------------

def check_columns(incoming: list[str], expected: list[str]) -> None:
    """Refuses a file that is not the same shape, naming what differs.

    Order is allowed to differ - the rows are reordered on the way in - but the set of
    names is not. A file missing a column would import it as NULL for every new row,
    and one with an extra column has information that would be dropped on the floor;
    both are things the reader should decide about, not discover months later.
    """
    missing = [c for c in expected if c not in set(incoming)]
    extra = [c for c in incoming if c not in set(expected)]
    if missing or extra:
        raise AppendProblem(
            "append_columns_differ",
            "The file's columns do not match this dataset",
            missing=missing,
            extra=extra,
        )
    if len(set(incoming)) != len(incoming):
        raise AppendProblem("append_columns_repeated", "The file repeats a column name")


def stage(
    source: Path,
    destination: Path,
    encoding: str,
    delimiter: str,
    has_header: bool,
    expected: list[str],
    on_progress: Optional[Callable[[int], None]] = None,
) -> int:
    """Writes the uploaded file out as a stored batch, and returns how many rows.

    Reordered into the dataset's column order and written without a header, so replaying
    it later is positional and needs to remember nothing about where it came from.

    Streamed a row at a time like the rest of the ingest path: a batch is as capable of
    being hundreds of megabytes as a first upload is.
    """
    written = 0
    with open(source, encoding=encoding, errors="replace", newline="") as fin, open(
        destination, "w", encoding="utf-8", newline=""
    ) as fout:
        reader = csv.reader(fin, delimiter=delimiter)
        writer = csv.writer(fout, delimiter=BATCH_DELIMITER, quoting=csv.QUOTE_MINIMAL)

        first = ingestion.without_bom(next(reader, []))
        if has_header:
            check_columns(first, expected)
            order = [first.index(c) for c in expected]
        else:
            if len(first) != len(expected):
                raise AppendProblem(
                    "append_width_differs",
                    f"The file has {len(first)} columns; this dataset has {len(expected)}",
                    found=len(first),
                    expected=len(expected),
                )
            order = list(range(len(expected)))
            writer.writerow([first[i] if i < len(first) else "" for i in order])
            written = 1

        for row in reader:
            writer.writerow([row[i] if i < len(row) else "" for i in order])
            written += 1
            if on_progress and written % 200_000 == 0:
                on_progress(written)
    if on_progress:
        on_progress(written)
    return written


# ---- loading a stored batch into the table ----------------------------------------

def _load(dataset_id: str, path: Path, columns: list[str], key_cols: list[str]) -> dict:
    """Loads one stored batch into raw_data. Caller holds the write lock.

    With a key, rows already present are removed first and the incoming values take
    their place. The DELETE is a single set operation against the staged table rather
    than a statement per row, which is the difference between seconds and hours on a
    batch of any size.
    """
    cur = datasets.cursor(dataset_id)
    quoted = ", ".join(sql_utils.quote_ident(c) for c in columns)
    escaped = str(path).replace("'", "''")
    names = ", ".join(f"'{c.replace(chr(39), chr(39) * 2)}'" for c in columns)

    cur.execute("DROP TABLE IF EXISTS incoming_batch")
    cur.execute(
        f"""
        CREATE TABLE incoming_batch AS
        SELECT * FROM read_csv(
            '{escaped}',
            delim=',', header=false, quote='"', escape='"',
            strict_mode=false, null_padding=true, ignore_errors=true,
            sample_size=-1, all_varchar=true, parallel=false,
            names=[{names}]
        )
        """
    )
    incoming = cur.execute("SELECT COUNT(*) FROM incoming_batch").fetchone()[0]

    replaced = 0
    if key_cols:
        # the same expression reads correctly against either table: both carry the key
        # columns under the same names
        key_expr = row_identity.key_expression(key_cols)
        replaced = cur.execute(
            f"""
            SELECT COUNT(*) FROM raw_data
            WHERE {key_expr} IN (SELECT {key_expr} FROM incoming_batch)
            """
        ).fetchone()[0]
        cur.execute(
            f"""
            DELETE FROM raw_data
            WHERE {key_expr} IN (SELECT {key_expr} FROM incoming_batch)
            """
        )

    cur.execute(f"INSERT INTO raw_data ({quoted}) SELECT {quoted} FROM incoming_batch")
    cur.execute("DROP TABLE IF EXISTS incoming_batch")
    return {"incoming": incoming, "replaced": replaced}


def apply_batch(dataset_id: str, path: Path, dataset: dict) -> dict:
    """Loads one stored batch, taking the write lock."""
    columns = sql_utils.table_columns(dataset_id, "raw_data")
    key_cols = row_identity.key_columns(dataset)
    with datasets.write_lock(dataset_id):
        return _load(dataset_id, path, columns, key_cols)


def replay_batches(dataset_id: str, dataset: dict) -> int:
    """Re-applies every stored batch, in order. Returns how many rows arrived.

    Called after the import rebuilds raw_data from the original upload. Order matters:
    batch 2 may replace a record batch 1 added, and replaying them out of order would
    leave the older statement in place.
    """
    files = batch_files(dataset_id)
    if not files:
        return 0
    columns = sql_utils.table_columns(dataset_id, "raw_data")
    key_cols = row_identity.key_columns(dataset)
    total = 0
    with datasets.write_lock(dataset_id):
        for path in files:
            total += _load(dataset_id, path, columns, key_cols)["incoming"]
    return total


# ---- putting the derived table back ------------------------------------------------

def rebuild_cleaned(dataset_id: str) -> Optional[dict]:
    """Re-runs the most recent cleaning so the cleaned view includes the new rows.

    Without this the cleaned table keeps whatever it had, and a reader looking at the
    cleaned source sees a row count that stopped moving - the new records are simply
    absent, with nothing on screen to say why. The configuration is already recorded
    for every clean that has run (catalog.list_cleaning_operations), so there is
    nothing to ask the user again.
    """
    if not sql_utils.table_exists(dataset_id, "cleaned_data"):
        return None
    history = catalog.list_cleaning_operations(dataset_id)
    if not history:
        return None

    # imported here rather than at module scope: cleaning imports sql_utils which
    # imports the schemas, and appending is imported from ingestion's job path
    from app.models.schemas import CleaningConfig
    from app.services import cleaning

    config = history[0].get("config_json")
    if isinstance(config, str):
        config = json.loads(config)
    if not isinstance(config, dict):
        return None
    return cleaning.apply_cleaning(dataset_id, CleaningConfig(**config)).model_dump()
