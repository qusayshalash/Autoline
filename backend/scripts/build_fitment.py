"""Build the filter-fitment reference database from Dataprime's catalogue work.

    python scripts/build_fitment.py <outputs dir> <Dataprime dir>

<outputs dir> holds the merged file - for each of the registry's 79,580 vehicle
configurations, what MANN-FILTER, UFI (direct, and by UFI's official MANN
cross-reference), JS Filter and Denckermann each fit - with UFI's cross-reference table
and MANN's OE references. <Dataprime dir> holds the JS Filter and Denckermann OE
numbers (dataset.db, denckermann.db) and normalize.py, whose make parser is reused so a
vehicle's make is read exactly as it was when the data was gathered.

A configuration is identified by SHA-256 over seven registry fields (app/services/
fitment.py); recomputing it for all 4,114,487 registry vehicles reproduced the file's own
key for every one.

Whether the catalogues agree is decided here, once, and stored - the method is
Dataprime's agreement.py, ported as it stands because its notes record why simpler ones
failed. Every part is resolved to the set of original-equipment (car maker) numbers it
answers to; two catalogues agree on a filter when their parts share an OE number of the
vehicle's own make, disagree when both are referenced and share none, and are
"unlinked" when either part has no reference - silence is not evidence either way. A
union-find over the cross-references was tried first and chained 76% of all codes into
one group, so links are kept to one hop (two through a UFI product as pivot).

The output goes to <data dir>/reference/fitment.duckdb - beside the datasets, never in
git: it is catalogue data gathered from the makers' sites, the app's to read and not the
repository's to publish. Rebuilding replaces it whole.
"""

import collections
import csv
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb  # noqa: E402

from app.services import fitment  # noqa: E402

MERGED = "mann_ufi_jsfilter_denckermann_ufi_alternatives_configuration_fitment.csv"
UFI_XREF = "ufi_cross_references_full.csv"
MANN_OE_FILES = [
    ("mann_filter_vehicle_oem_references.csv", "mann_part_number", "oe_manufacturer", "oe_number_normalized"),
    ("mann_filter_oem_references.csv", "mann_part_number", "reference_manufacturer", "reference_number"),
]

# the four catalogues compared, and each one's column prefix in the merged file
COMPARED = {"mann": "", "ufi": "ufi_", "jsfilter": "jsfilter_", "denckermann": "denckermann_"}
TYPE_COLUMNS = {"oil": "oil", "air": "air", "fuel": "fuel", "cabin": "cabin_air"}

_SUFFIX = re.compile(r"_(MANN-FILTER|UFI|JS|DENCKERMANN)$", re.I)
# statements about the vehicle, not part numbers
NOT_A_PART = {"NOFILTER", "LIFETIMEFILTER", "NONE", "NA", ""}
# filter brands, as against car makers: a cross-reference to one of these is not an OE number
AFTERMARKET = {
    "UFI", "SOFIMA", "MANN+HUMMEL", "BOSCH", "KNECHT-MAHLE", "FRAM", "HENGST",
    "PURFLUX", "MECAFILTER", "CLEAN FILTERS", "TECNOCAR", "FILTRON", "ALCO FILTERS",
    "COOPERSFIAAM", "DONALDSON", "ADL (BLUEPRINT)", "FLEETGUARD", "WIX EUROPE",
    "WIX", "HIFI FILTER", "CASTROL", "COMLINE", "CHAMPION", "DELPHI", "VALEO",
    "MAHLE", "KNECHT", "BALDWIN", "SAKURA", "NIPPARTS", "ASHIKA", "JAPANPARTS",
    "BLUE PRINT", "MAPCO", "MEAT & DORIA", "MISFAT", "OPEN PARTS", "AUTOMEGA",
    "KAMOKA", "MAXGEAR", "STARLINE", "DENCKERMANN", "JS ASAKASHI", "MULLER FILTER",
}

csv.field_size_limit(10**9)


def norm(code) -> str:
    c = _SUFFIX.sub("", (code or "").strip())
    return re.sub(r"[^A-Z0-9]", "", c.upper())


def split_parts(cell) -> list[str]:
    return [n for n in (norm(p) for p in re.split(r"[;,]", cell or "")) if n and n not in NOT_A_PART]


class References:
    """Every part in one namespace: the OE numbers it answers to, with their maker."""

    def __init__(self):
        self.oe: dict[str, set] = collections.defaultdict(set)

    def add(self, part, maker, oe):
        self.oe[part].add((maker, oe))

    def same(self, a, b, marque):
        """True, False, or None when the comparison cannot be made."""
        if a == b:
            return True
        ra, rb = self.oe.get(a), self.oe.get(b)
        if not ra or not rb:
            return None
        if marque:
            def mine(pairs):
                # "MERCEDES-BENZ" here, "MERCEDES BENZ" there
                return {c for m, c in pairs if m and (m.startswith(marque[:5]) or marque.startswith(m[:5]))}

            ra, rb = mine(ra), mine(rb)
            if not ra or not rb:
                return None
        else:
            ra, rb = {c for _, c in ra}, {c for _, c in rb}
        return bool(ra & rb)


def references(outputs: Path, dataprime: Path) -> References:
    refs = References()
    oe_maker = {}

    # UFI product -> its OE numbers, and the aftermarket codes (MANN among them) sharing it
    prod_oe, prod_am = collections.defaultdict(set), collections.defaultdict(set)
    with open(outputs / UFI_XREF, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            prod, code = norm(r.get("ufi_product_code")), norm(r.get("cross_code"))
            if not prod or not code or code in NOT_A_PART:
                continue
            maker = (r.get("manufacturer") or "").strip().upper()
            (prod_am[prod].add(code) if maker in AFTERMARKET else prod_oe[prod].add((maker, code)))
    for prod, oes in prod_oe.items():
        for maker, oe in oes:
            refs.add(prod, maker, oe)
        for code in prod_am.get(prod, ()):
            for maker, oe in oes:
                refs.add(code, maker, oe)

    for name, pcol, mcol, ocol in MANN_OE_FILES:
        path = outputs / name
        if not path.is_file():
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                part, oe = norm(r.get(pcol)), norm(r.get(ocol))
                maker = (r.get(mcol) or "").strip().upper()
                if part and oe and maker not in AFTERMARKET:
                    refs.add(part, maker, oe)
                    oe_maker.setdefault(oe, maker)

    db = sqlite3.connect(f"file:{dataprime / 'dataset.db'}?mode=ro", uri=True)
    for part, maker, oe in db.execute(
        "SELECT f.part_number, po.oe_brand, po.oe_part_no FROM part_oe po JOIN filter_part f USING (filter_id)"
    ):
        if norm(part) and norm(oe):
            refs.add(norm(part), (maker or "").strip().upper(), norm(oe))
            oe_maker[norm(oe)] = (maker or "").strip().upper()
    db.close()

    # Denckermann was searched BY OE number, so the maker is that number's
    db = sqlite3.connect(f"file:{dataprime / 'denckermann.db'}?mode=ro", uri=True)
    for oe, part in db.execute("SELECT oe_query, part_no FROM result"):
        if norm(part) and norm(oe):
            refs.add(norm(part), oe_maker.get(norm(oe), ""), norm(oe))
    db.close()
    return refs


def verdicts(merged: Path, refs: References, parse_manufacturer) -> list[tuple]:
    """(configuration_key, type, verdict, disagreeing pairs) for every configuration."""
    out = []
    with open(merged, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            made = parse_manufacturer(r.get("tozeret_nm", ""))
            marque = made[0].upper() if made else None
            for kind, col in TYPE_COLUMNS.items():
                picks = {}
                for source, prefix in COMPARED.items():
                    parts = split_parts(r.get(f"{prefix}{col}_filter_parts", ""))
                    if parts:
                        picks[source] = parts
                if not picks:
                    continue
                if len(picks) == 1:
                    out.append((r["configuration_key"], kind, "single", ""))
                    continue
                names = sorted(picks)
                agreed, clashes = False, []
                for i, a in enumerate(names):
                    for b in names[i + 1 :]:
                        # alternatives on either side: one match is enough
                        verdict = None
                        for pa in picks[a]:
                            for pb in picks[b]:
                                v = refs.same(pa, pb, marque)
                                if v is True:
                                    verdict = True
                                elif v is False and verdict is None:
                                    verdict = False
                        if verdict is True:
                            agreed = True
                        elif verdict is False:
                            clashes.append(f"{a}|{b}")
                verdict = "disagree" if clashes else "agree" if agreed else "unlinked"
                out.append((r["configuration_key"], kind, verdict, ";".join(clashes)))
    return out


def build(outputs: Path, dataprime: Path, out: Path | None = None) -> dict:
    out = out or fitment.database_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    merged = outputs / MERGED

    sys.path.insert(0, str(dataprime))
    from normalize import parse_manufacturer  # noqa: E402  (Dataprime's own make parser)

    rows = verdicts(merged, references(outputs, dataprime), parse_manufacturer)

    con = duckdb.connect(str(tmp))
    try:
        con.execute(
            "CREATE TABLE config AS SELECT * FROM read_csv(?, header=true, all_varchar=true, sample_size=-1)",
            [str(merged)],
        )
        con.execute("CREATE UNIQUE INDEX config_key ON config (configuration_key)")
        con.execute("CREATE TABLE verdict (configuration_key VARCHAR, kind VARCHAR, verdict VARCHAR, clashes VARCHAR)")
        con.executemany("INSERT INTO verdict VALUES (?, ?, ?, ?)", rows)
        con.execute("CREATE INDEX verdict_key ON verdict (configuration_key)")
        configs, vehicles = con.execute(
            "SELECT COUNT(*), SUM(TRY_CAST(vehicle_count AS BIGINT)) FROM config"
        ).fetchone()
        by_verdict = con.execute(
            """
            SELECT v.kind, v.verdict, SUM(TRY_CAST(c.vehicle_count AS BIGINT))
            FROM verdict v JOIN config c USING (configuration_key) GROUP BY ALL ORDER BY 1, 2
            """
        ).fetchall()
    finally:
        con.close()

    tmp.replace(out)
    fitment.reset()
    return {"configurations": configs, "vehicles": vehicles, "verdicts": by_verdict, "path": str(out)}


if __name__ == "__main__":
    result = build(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"{result['configurations']:,} configurations, {result['vehicles']:,} vehicles -> {result['path']}")
    for kind, verdict, n in result["verdicts"]:
        print(f"  {kind:6} {verdict:9} {n:>10,}")
