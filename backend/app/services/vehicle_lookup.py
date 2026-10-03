"""One vehicle, found by its plate or its chassis number.

The rest of the app answers questions about many rows at once. This answers the question
somebody at a counter actually asks - "what is this car?" - and has to accept the number
the way it is said aloud or read off a document, not the way the registry stores it.

What the registry stores was measured rather than assumed, across all 4,114,487 rows:

  * **Plates are always eight characters, zero-padded.** "04910766" is stored for a plate
    printed and spoken as 49-107-66, and 45% of all plates start with that zero. Seven
    digits typed have to find the eight stored, and so do the dashes people type because
    the plate has them.
  * **Chassis numbers run from 16 to 20 characters**, not the 17 a modern VIN has, and are
    all upper case. Two of them occur twice in the file, so a lookup can honestly return
    more than one vehicle and the screen has to be able to say so.

Both columns are read from `raw_data`: the file plus every correction, and the whole of
it. The cleaned copy may have filtered a vehicle out or dropped a column, and a lookup
that cannot find a car because of how somebody once tidied the table would be wrong in a
way nobody could see.

Measured cost: about 25 ms per lookup on the full registry, with no index.
"""

import re
from typing import Optional

from app.db import catalog
from app.db.connection import datasets
from app.services import sql_utils

PLATE_COLUMN = "mispar_rechev"
CHASSIS_COLUMN = "misgeret"

# The registry pads every plate to this width.
PLATE_WIDTH = 8

# Enough for the duplicated chassis numbers that exist, and a ceiling on what one
# lookup can return across several datasets.
MAX_MATCHES = 10


def interpret(query: str) -> tuple[Optional[str], Optional[str]]:
    """What was typed, as (plate, chassis) - at most one of them set.

    Digits alone, eight or fewer, are a plate: dashes, spaces and dots are how a plate is
    written, so they are dropped. Anything with a letter is a chassis number, since every
    chassis number in the file has letters; so is a run of digits too long to be a plate.
    """
    text = (query or "").strip()
    if not text:
        return None, None
    compact = re.sub(r"[\s.\-_/]", "", text)
    if compact.isdigit():
        if len(compact) <= PLATE_WIDTH:
            return compact.zfill(PLATE_WIDTH), None
        return None, compact
    if re.fullmatch(r"[A-Za-z0-9]+", compact):
        return None, compact.upper()
    return None, None


def lookup(query: str) -> dict:
    """Every vehicle matching the query, across every dataset that can answer it."""
    plate, chassis = interpret(query)
    if plate is None and chassis is None:
        return {"query": query, "kind": None, "normalized": "", "matches": []}

    column, value = (PLATE_COLUMN, plate) if plate else (CHASSIS_COLUMN, chassis)
    matches: list[dict] = []
    for ds in catalog.list_datasets():
        if ds.get("status") != "ready":
            continue
        dataset_id = ds["id"]
        with datasets.reading(dataset_id) as cur:
            if not sql_utils.table_exists(dataset_id, "raw_data"):
                continue
            columns = sql_utils.table_columns(dataset_id, "raw_data")
            if column not in columns:
                continue
            rows = cur.execute(
                f"SELECT * FROM raw_data WHERE {sql_utils.quote_ident(column)} = ? LIMIT ?",
                [value, MAX_MATCHES - len(matches)],
            ).fetchall()
        for row in rows:
            matches.append(
                {
                    "dataset_id": dataset_id,
                    "dataset_name": ds.get("original_filename") or "",
                    "columns": columns,
                    "values": ["" if v is None else str(v) for v in row],
                }
            )
        if len(matches) >= MAX_MATCHES:
            break

    return {
        "query": query,
        "kind": "plate" if plate else "chassis",
        "normalized": value,
        "matches": matches,
    }
