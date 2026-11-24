"""Which filters fit a vehicle - from four catalogues, with what each one says.

A vehicle is looked up by its configuration: SHA-256 over seven of its registry fields,
joined with the unit separator. The recipe is the merged catalogue file's own, verified
by recomputing it for all 4,114,487 registry vehicles - every one matched - so it reaches
cars registered after the catalogues were gathered, as long as their configuration was
already known.

Every source is reported separately and nothing is merged into a single answer here:
which part to trust, and how to show disagreement, is the card's question. A part list
is "W610/3_MANN-FILTER;W610/6_MANN-FILTER" in the file - several entries are alternatives
the catalogue gives for the same vehicle, not a contradiction.

A missing part is reported as missing. Nothing is inferred from a similar car: a wrong
filter damages an engine.
"""

import hashlib
import threading
from pathlib import Path
from typing import Optional

import duckdb

from app.config import settings

KEY_FIELDS = [
    "tozeret_cd",
    "sug_degem",
    "degem_cd",
    "degem_manoa",
    "shnat_yitzur",
    "sug_delek_nm",
    "kvutzat_zihum",
]
SEPARATOR = "\x1f"

TYPES = ["oil", "air", "fuel", "cabin"]
# each source's column for a filter type
SOURCES = {
    "mann": {"oil": "oil_filter_parts", "air": "air_filter_parts", "fuel": "fuel_filter_parts", "cabin": "cabin_air_filter_parts"},
    "ufi": {t: f"ufi_direct_{c}" for t, c in {"oil": "oil_filter_parts", "air": "air_filter_parts", "fuel": "fuel_filter_parts", "cabin": "cabin_air_filter_parts"}.items()},
    "ufi_xref": {t: f"ufi_cross_reference_{c}" for t, c in {"oil": "oil_filter_parts", "air": "air_filter_parts", "fuel": "fuel_filter_parts", "cabin": "cabin_air_filter_parts"}.items()},
    "jsfilter": {t: f"jsfilter_{c}" for t, c in {"oil": "oil_filter_parts", "air": "air_filter_parts", "fuel": "fuel_filter_parts", "cabin": "cabin_air_filter_parts"}.items()},
    "denckermann": {t: f"denckermann_{c}" for t, c in {"oil": "oil_filter_parts", "air": "air_filter_parts", "fuel": "fuel_filter_parts", "cabin": "cabin_air_filter_parts"}.items()},
}
# how each source matched the vehicle, kept with its parts
MATCH = {
    "mann": ("mann_match_status", "mann_match_method"),
    "ufi": ("ufi_direct_match_status", "ufi_direct_match_confidence"),
    "jsfilter": ("jsfilter_match_status", "jsfilter_match_confidence"),
    "denckermann": ("denckermann_match_status", "denckermann_match_confidence"),
}

_lock = threading.Lock()
_con: Optional[duckdb.DuckDBPyConnection] = None


def database_path() -> Path:
    return settings.data_dir / "reference" / "fitment.duckdb"


def reset() -> None:
    """Forget the open database, so a rebuilt one is read next time."""
    global _con
    with _lock:
        if _con is not None:
            _con.close()
        _con = None


def _cursor() -> Optional[duckdb.DuckDBPyConnection]:
    global _con
    with _lock:
        if _con is None:
            path = database_path()
            if not path.is_file():
                return None
            _con = duckdb.connect(str(path), read_only=True)
        return _con.cursor()


def available() -> bool:
    return database_path().is_file()


def config_key(record: dict) -> str:
    joined = SEPARATOR.join(str(record.get(f) or "") for f in KEY_FIELDS)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def parse_parts(value: Optional[str]) -> list[dict]:
    """"W610/3_MANN-FILTER;HU711/51X_MANN-FILTER" -> [{part, brand}, ...]."""
    out = []
    for item in (value or "").split(";"):
        item = item.strip()
        if not item:
            continue
        part, _, brand = item.rpartition("_") if "_" in item else (item, "", "")
        out.append({"part": part or item, "brand": brand or None})
    return out


def lookup(record: dict) -> Optional[dict]:
    """Every catalogue's filters for this vehicle, or None when the reference database is
    not installed. `found` is false when its configuration is not in the catalogues."""
    cur = _cursor()
    if cur is None:
        return None
    key = config_key(record)
    row = cur.execute("SELECT * FROM config WHERE configuration_key = ?", [key]).fetchone()
    if row is None:
        return {"configuration": key, "found": False, "covered": False, "filters": {}, "matches": {}, "verdicts": {}}
    data = dict(zip([d[0] for d in cur.description], row))

    filters = {
        t: {src: parse_parts(data.get(cols[t])) for src, cols in SOURCES.items() if data.get(cols[t])}
        for t in TYPES
    }
    # decided at build time (scripts/build_fitment.py): agree, disagree, unlinked, single
    verdicts = {}
    try:
        for kind, verdict, clashes in cur.execute(
            "SELECT kind, verdict, clashes FROM verdict WHERE configuration_key = ?", [key]
        ).fetchall():
            verdicts[kind] = {"verdict": verdict, "clashes": [c for c in (clashes or "").split(";") if c]}
    except duckdb.CatalogException:
        pass  # a database built before verdicts were stored
    return {
        "configuration": key,
        "found": True,
        "covered": data.get("combined_fitment_coverage") == "covered",
        "electric": data.get("vehicle_powertrain") == "full_electric",
        "vehicles": int(data["vehicle_count"]) if (data.get("vehicle_count") or "").isdigit() else None,
        "sources": [s for s in (data.get("fitment_sources") or "").split(";") if s],
        "filters": {t: f for t, f in filters.items() if f},
        "verdicts": verdicts,
        "matches": {
            src: {"status": data.get(a), "detail": data.get(b)}
            for src, (a, b) in MATCH.items()
            if data.get(a)
        },
    }
