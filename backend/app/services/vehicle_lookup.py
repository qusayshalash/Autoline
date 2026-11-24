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
from app.services import clocks, fitment, removals, row_identity, sql_utils, vin

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
            found = []
            for row in rows:
                values = ["" if v is None else str(v) for v in row]
                record = dict(zip(columns, values))
                # a vehicle the registry has dropped is still found - and said to be gone
                key = row_identity.row_key_values(ds, record)
                gone = removals.for_row(dataset_id, key) if key else None
                found.append((values, record, gone))
        for values, record, gone in found:
            matches.append(
                {
                    "dataset_id": dataset_id,
                    "dataset_name": ds.get("original_filename") or "",
                    "columns": columns,
                    "values": values,
                    "vin": vin.read(record),
                    "removed_at": clocks.iso(gone) if gone else None,
                    "fitment": fitment.lookup(record),
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


# ---- how many like it -------------------------------------------------------------------
#
# "How many cars like this one are on the road?" is the question a parts trader asks next:
# it is the size of the market for whatever fits this car. Two answers, from wide to
# narrow: the same make and model, and of those the ones with this engine - the engine is
# what decides most filters.
#
# Counted in the table the grid shows (the cleaned copy when there is one), with the
# grid's own filter builder, so the number on the card is the number of rows the link
# opens - never a figure the grid then contradicts.

MAKE_COLUMN = "tozeret_nm"
TRADE_NAME_COLUMN = "kinuy_mishari"
MODEL_CODE_COLUMN = "degem_nm"
ENGINE_COLUMN = "degem_manoa"


def similar(dataset_id: str, query: str) -> dict:
    """{"model": {filters, count} | None, "engine": {filters, count} | None} for the
    vehicle `query` finds in this dataset. None where the vehicle lacks the field."""
    from app.models.schemas import FilterRule
    from app.services import view

    empty = {"model": None, "engine": None}
    ds = catalog.get_dataset(dataset_id)
    if ds is None or ds.get("status") != "ready":
        raise LookupError(dataset_id)

    plate, chassis = interpret(query)
    if plate is None and chassis is None:
        return empty
    column, value = (PLATE_COLUMN, plate) if plate else (CHASSIS_COLUMN, chassis)

    with datasets.reading(dataset_id) as cur:
        if not sql_utils.table_exists(dataset_id, "raw_data"):
            return empty
        raw_columns = sql_utils.table_columns(dataset_id, "raw_data")
        if column not in raw_columns:
            return empty
        row = cur.execute(
            f"SELECT * FROM raw_data WHERE {sql_utils.quote_ident(column)} = ? LIMIT 1", [value]
        ).fetchone()
        if row is None:
            return empty
        car = {c: ("" if v is None else str(v).strip()) for c, v in zip(raw_columns, row)}

        table = sql_utils.resolve_source_table(dataset_id, "cleaned")
        columns = sql_utils.table_columns(dataset_id, table)

        # the trade name ("COROLLA") is what people mean by the model; the registry's
        # model code stands in only when a row has no trade name
        model_column = next(
            (c for c in (TRADE_NAME_COLUMN, MODEL_CODE_COLUMN) if car.get(c) and c in columns), None
        )
        if not car.get(MAKE_COLUMN) or MAKE_COLUMN not in columns or model_column is None:
            return empty

        def count(rules: list[dict]) -> int:
            where, params = view.where(
                dataset_id, columns, filters=[FilterRule(op="eq", **r) for r in rules]
            )
            return cur.execute(
                f"SELECT COUNT(*) FROM {sql_utils.quote_ident(table)} WHERE {where}", params
            ).fetchone()[0]

        model_rules = [
            {"column": MAKE_COLUMN, "value": car[MAKE_COLUMN]},
            {"column": model_column, "value": car[model_column]},
        ]
        out = {"model": {"filters": model_rules, "count": count(model_rules)}, "engine": None}
        if car.get(ENGINE_COLUMN) and ENGINE_COLUMN in columns:
            engine_rules = model_rules + [{"column": ENGINE_COLUMN, "value": car[ENGINE_COLUMN]}]
            out["engine"] = {"filters": engine_rules, "count": count(engine_rules)}
        return out
