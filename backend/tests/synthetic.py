"""Builds the small CSV the integration tests run against, and reads it back with
Python's own csv module so every expected number has an origin outside the system
under test.

The file deliberately reproduces the awkward parts of the real 4.1M-row registry
rather than being clean sample data, because clean sample data never catches the
bugs that actually happen here:

  * cp1255 (Hebrew) bytes, pipe-delimited - the production dialect
  * identifiers with leading zeros, which any numeric inference destroys
  * blank fields, which must become a visible "unspecified" bucket, not vanish
  * a maker whose name is the tail of a country name, the `contains`/`starts_with`
    trap ("kia" is the last three letters of "Turkey" in Hebrew)
  * fields holding a comma, a double quote, a newline, and LIKE wildcards
  * two byte-identical rows, so dedupe has something real to remove
  * a year column with a non-numeric value in it
"""

import csv
from pathlib import Path

ENCODING = "cp1255"
DELIMITER = "|"

COLUMNS = [
    "mispar_rechev",   # id, zero-padded
    "tozeret_nm",      # maker
    "sug_delek_nm",    # fuel
    "baalut",          # ownership
    "shnat_yitzur",    # year
    "tzeva_rechev",    # colour
    "ramat_gimur",     # trim
]

KIA = "קיה ישראל"
TURKEY = "טורקיה יבוא"       # ends with the same three letters as KIA starts with
TOYOTA = "טויוטה יפן"
HYUNDAI = "יונדאי קוריאה"

MAKERS = [KIA, TURKEY, TOYOTA, HYUNDAI, ""]
FUELS = ["בנזין", "דיזל", "חשמל", "היברידי", ""]
OWNERS = ["פרטי", "חברה", "ליסינג"]
YEARS = ["2018", "2019", "2020", "2021", "2022", "2023"]
COLOURS = ["לבן", "שחור", "כסף"]
TRIMS = ["L", "EX", ""]

# Rows that exist to break something specific. Their ids sit at 000090xx, clear of
# the grid's 00000001..00000480, so a test naming one of them selects only it.
# Each is annotated with what it is for.
EDGE_ROWS = [
    # leading zeros must survive as text, not become 42
    ["00009042", KIA, "בנזין", "פרטי", "2020", "לבן", "L"],
    # a comma inside a field - forces quoting in any comma-delimited export
    ["00009043", TOYOTA, "דיזל", "חברה", "2021", "שחור, מטאלי", "EX"],
    # a double quote inside a field - forces quoting *and* doubling
    ["00009044", TOYOTA, "דיזל", "חברה", "2021", 'גלגלי 15" אלומיניום', "EX"],
    # a newline inside a field - one record spanning two physical lines
    ["00009045", HYUNDAI, "חשמל", "פרטי", "2022", "כסף\nבהיר", "L"],
    # LIKE wildcards as literal characters - contains/starts_with must not treat
    # these as wildcards
    ["00009046", HYUNDAI, "חשמל", "ליסינג", "2022", "50%_ספיישל", "EX"],
    # a year column that is not a year
    ["00009047", KIA, "היברידי", "פרטי", "לא ידוע", "לבן", "L"],
    # everything blank except the id
    ["00009048", "", "", "", "", "", ""],
    # two byte-identical rows for dedupe
    ["00009049", KIA, "בנזין", "פרטי", "2019", "שחור", "L"],
    ["00009049", KIA, "בנזין", "פרטי", "2019", "שחור", "L"],
]

GRID_ROWS = 480


def _grid() -> list[list[str]]:
    """A deterministic spread over the value space. The moduli are coprime with each
    other where it matters, so the cross-tabs come out uneven - an even matrix would
    hide an off-by-one in a row or column total."""
    rows = []
    for i in range(GRID_ROWS):
        rows.append(
            [
                f"{i + 1:08d}",
                MAKERS[i % 5],
                FUELS[i % 4] if i % 11 else "",
                OWNERS[i % 3],
                YEARS[i % 6],
                COLOURS[i % 3],
                TRIMS[i % 7 % 3],
            ]
        )
    return rows


def write(path: Path) -> Path:
    """Writes the file in the production dialect and returns its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=ENCODING, newline="") as f:
        w = csv.writer(f, delimiter=DELIMITER, quoting=csv.QUOTE_MINIMAL)
        w.writerow(COLUMNS)
        for row in _grid() + EDGE_ROWS:
            w.writerow(row)
    return path


def read_back(path: Path) -> list[dict[str, str]]:
    """The oracle: what the file says, according to Python, not according to DuckDB."""
    with open(path, encoding=ENCODING, newline="") as f:
        return list(csv.DictReader(f, delimiter=DELIMITER))


def counts(rows: list[dict[str, str]], column: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[column]] = out.get(r[column], 0) + 1
    return out


def cross(rows: list[dict[str, str]], row_col: str, col_col: str) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for r in rows:
        key = (r[row_col], r[col_col])
        out[key] = out.get(key, 0) + 1
    return out
