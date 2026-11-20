"""Reading a chassis number (VIN) against the registry's own record of the vehicle.

Seventeen characters, of which only some are universal: 1-3 (the WMI) name the maker,
10 is the model year where the maker uses it, 9 is a check digit where the maker uses it,
4-8 describe the vehicle in the maker's own terms, and 12-17 are the serial. Which of
those hold for which maker was measured on the registry, not taken from a reference -
see scripts/build_vin_table.py for what was found and why. This module judges a vehicle
only by the rules that held for its prefix, and says "unchecked" for the rest rather
than guessing.

What it catches: a VIN whose prefix belongs to another make than the registry files the
car under (a number typed into the wrong record, or one that is not this car's) - the
one finding called "bad". Worth a look, but no more: a model year two or more from the
registry's, a model code that differs where the maker always writes it, a broken check
digit. A year one off is normal - a car built late in the year carries the next model
year - and is not reported. Measured on the full registry (4,114,487 vehicles): 35 bad, 2,874 worth a look.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

TABLE = Path(__file__).resolve().parent.parent / "data" / "vin_table.json"

VIN_LENGTH = 17
# I, O and Q are never used, so they cannot be mistaken for 1 and 0
ALLOWED = set("ABCDEFGHJKLMNPRSTUVWXYZ0123456789")
# the model-year code repeats every 30 years: A is 1980 and 2010, 9 is 2009 and 2039
YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"

# ISO 3779 check digit: each character's value, times its position's weight, mod 11
_VALUES = {
    **{str(d): d for d in range(10)},
    **dict(zip("ABCDEFGH", range(1, 9))),
    **dict(zip("JKLMN", range(1, 6))),
    "P": 7,
    "R": 9,
    **dict(zip("STUVWXYZ", range(2, 10))),
}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

MAKE = "tozeret_nm"
MODEL = "degem_nm"
YEAR = "shnat_yitzur"
CHASSIS = "misgeret"


def brand(make: str) -> str:
    """The brand alone, for comparing makes. The registry files a make with where it was
    built - "מרצדס בנץ גרמנ", "מרצדס-בנץ אוסט" - and one WMI covers several plants, so the
    whole value would call an Austrian-built G-Class a stranger to Mercedes' own prefix."""
    words = make.replace("-", " ").split()
    return words[0] if words else ""


def well_formed(vin: str) -> bool:
    return len(vin) == VIN_LENGTH and set(vin) <= ALLOWED


def model_year(code: str, near: Optional[int]) -> Optional[int]:
    """The model year a 10th character stands for - of its two readings 30 years apart,
    the one nearest `near` (the registry's year). None for a character that is no year."""
    if code not in YEAR_CODES:
        return None
    first = 1980 + YEAR_CODES.index(code)
    candidates = [first, first + 30]
    if near is None:
        return candidates[0]
    return min(candidates, key=lambda y: abs(y - near))


def check_digit_ok(vin: str) -> bool:
    total = sum(_VALUES.get(c, 0) * w for c, w in zip(vin, _WEIGHTS))
    expected = "X" if total % 11 == 10 else str(total % 11)
    return vin[8] == expected


@lru_cache(maxsize=1)
def table() -> dict:
    try:
        return json.loads(TABLE.read_text(encoding="utf-8")).get("prefixes", {})
    except FileNotFoundError:
        return {}


def _int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def read(record: dict) -> Optional[dict]:
    """What the vehicle's chassis number says, checked against the rest of `record`
    (column -> value). None when the record has no chassis number at all."""
    raw = str(record.get(CHASSIS) or "").strip().upper()
    if not raw:
        return None
    if not well_formed(raw):
        # older numbers run 16-20 characters in the registry; no standard to read them by
        return {"vin": raw, "standard": False, "verdict": "nonstandard"}

    prefix = raw[:3]
    rules = table().get(prefix)
    make = str(record.get(MAKE) or "").strip()
    model = str(record.get(MODEL) or "").strip().upper()
    year = _int(record.get(YEAR))
    decoded_year = model_year(raw[9], year)

    out = {
        "vin": raw,
        "standard": True,
        "wmi": prefix,
        "known": rules is not None,
        "model_code": raw[3:8],
        "year_code": raw[9],
        "serial": raw[11:],
        "maker": {"makes": [], "registry": make or None, "state": "unchecked"},
        "model": {"registry": model or None, "state": "unchecked"},
        "year": {"decoded": decoded_year, "registry": year, "state": "unchecked"},
        "check_digit": {"code": raw[8], "state": "unchecked"},
    }
    if rules is None:
        out["verdict"] = "unknown"
        return out

    out["maker"]["makes"] = rules["makes"]
    if make:
        known = {brand(m) for m in rules["makes"]}
        out["maker"]["state"] = "match" if brand(make) in known else "mismatch"

    if rules["model_code"] and model:
        out["model"]["state"] = "match" if raw[3 : 3 + len(model)] == model else "mismatch"

    if rules["year_code"] and year is not None and decoded_year is not None:
        gap = abs(decoded_year - year)
        out["year"]["state"] = "match" if gap == 0 else "near" if gap == 1 else "mismatch"

    if rules["check_digit"]:
        out["check_digit"]["state"] = "valid" if check_digit_ok(raw) else "invalid"

    # Only the make is grounds for "this is not the car": measured, a make outside its
    # prefix's is rare and isolated. The other disagreements come in clusters - 775
    # Thai-built Mitsubishis reading two years early, 324 Citroens four - which is how a
    # registry convention looks, not a wrong number; they are worth a look, no more.
    if out["maker"]["state"] == "mismatch":
        out["verdict"] = "bad"
    elif (
        out["year"]["state"] == "mismatch"
        or out["model"]["state"] == "mismatch"
        or out["check_digit"]["state"] == "invalid"
    ):
        out["verdict"] = "warn"
    else:
        out["verdict"] = "ok"
    return out
