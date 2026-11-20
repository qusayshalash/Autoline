"""Build app/data/vin_table.json - what each chassis-number prefix carries, measured.

    python scripts/build_vin_table.py <dataset_id>     (backend stopped: one writer)

A VIN's rules are only partly universal. Its first three characters (the WMI) name the
maker everywhere; the rest is each maker's own business - whether character 10 is the
model year, whether 4-8 carry the model code the registry files, whether 9 is a check
digit - and the makers that sell into Israel do not agree. Measured on the full registry
(4,114,487 rows, 3,780,906 with a 17-character VIN): the year code lands within a year of
the registry's for Hyundai, Kia, Skoda, Subaru or Honda on 98-100% of cars, and on 0-25%
for Toyota, Mazda, Nissan, Suzuki or Mercedes, which do not put the year there for cars
sold here. A fixed rule would have flagged several hundred thousand sound Toyotas.

So nothing here is asserted from a VIN reference: every rule is what the registry shows
for that prefix, and is kept only where it holds for nearly every car. The reader
(app/services/vin.py) judges a vehicle only against rules that passed.
"""

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connection import datasets  # noqa: E402
from app.services import vin  # noqa: E402

MIN_CARS = 100        # a prefix seen fewer times is left out: too few to know its rules
MAKE_SHARE = 0.0      # no share floor: sister brands (Omoda under Chery, a Subaru-built Toyota)
MAKE_MIN = 10         # are rare but real; ten cars or more is a pattern, fewer is the error sought
RULE_HOLDS = 0.99     # a rule is used for a prefix only where it holds this often

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "vin_table.json"


def main(dataset_id: str) -> None:
    with datasets.reading(dataset_id) as cur:
        rows = cur.execute(
            """
            SELECT misgeret, tozeret_nm, degem_nm, TRY_CAST(shnat_yitzur AS INT)
            FROM raw_data WHERE length(misgeret) = 17
            """
        ).fetchall()

    n = defaultdict(int)
    makes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    year_seen = defaultdict(int)
    year_near = defaultdict(int)
    model_seen = defaultdict(int)
    model_same = defaultdict(int)
    check_ok = defaultdict(int)

    for raw_vin, make, model, year in rows:
        v = (raw_vin or "").strip().upper()
        if not vin.well_formed(v):
            continue
        w = v[:3]
        n[w] += 1
        makes[w][(make or "").strip()] += 1
        if year:
            decoded = vin.model_year(v[9], year)
            if decoded is not None:
                year_seen[w] += 1
                year_near[w] += abs(decoded - year) <= 1
        if model and model.strip():
            model_seen[w] += 1
            model_same[w] += v[3 : 3 + len(model.strip())] == model.strip().upper()
        check_ok[w] += vin.check_digit_ok(v)

    table = {}
    for w, count in sorted(n.items()):
        if count < MIN_CARS:
            continue
        kept = sorted(
            (m for m, c in makes[w].items() if m and c >= MAKE_MIN and c / count >= MAKE_SHARE),
            key=lambda m: -makes[w][m],
        )
        table[w] = {
            "cars": count,
            "makes": kept,
            "year_code": year_seen[w] > 0 and year_near[w] / count >= RULE_HOLDS,
            "model_code": model_seen[w] > 0 and model_same[w] / model_seen[w] >= RULE_HOLDS,
            "check_digit": check_ok[w] / count >= RULE_HOLDS,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "measured_on": date.today().isoformat(),
                "vehicles": sum(n.values()),
                "rules_hold_at": RULE_HOLDS,
                "prefixes": table,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(table)} prefixes from {sum(n.values()):,} vehicles; "
        f"year code trusted for {sum(t['year_code'] for t in table.values())}, "
        f"model code for {sum(t['model_code'] for t in table.values())}, "
        f"check digit for {sum(t['check_digit'] for t in table.values())}"
    )


if __name__ == "__main__":
    main(sys.argv[1])
