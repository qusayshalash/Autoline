"""Characterization tests against the real vehicle registry.

These lock in figures that were established by hand, against the original 867 MB source
file, during a five-stage audit of the whole pipeline. They are not derived from the code
- if they were, they would agree with a broken version of it. They are what the file was
independently found to contain.

Their value is narrow and high: they are the only tests that would catch a change which
is correct on 489 synthetic rows and wrong on four million real ones - a sampling
shortcut, an approximation that only shows up at scale, a locale-dependent parse.

Opt in, because they need the developer's data directory and take longer than the rest:

    pytest -m real

They skip themselves - rather than fail - when the dataset is not present, so a checkout
on another machine still runs green.
"""

import os

import pytest

pytestmark = pytest.mark.real

# Established during the pipeline audit, from the original file rather than from the app.
TOTAL_ROWS = 4_114_487
KIA_ROWS = 426_259           # manufacturer starts with the marque, not merely contains it
KIA_PETROL_ROWS = 380_797
CLEANED_CSV_BYTES = 775_413_733   # a real export of every column, measured on disk


@pytest.fixture(scope="module")
def real():
    """The real dataset, reached through a client pointed at the developer's own data
    directory - deliberately outside the isolated test data dir the rest of the suite
    uses, and read-only throughout this module.
    """
    from app.config import Settings

    # REAL_DATA_DIR is set by conftest from the app's own configuration, before that
    # configuration is redirected at a temp directory for the rest of the suite.
    live = Settings(data_dir=os.environ["REAL_DATA_DIR"])
    catalog_path = live.catalog_path
    if not catalog_path.exists():
        pytest.skip(f"no catalog at {catalog_path}")

    conn = _open(catalog_path)
    try:
        rows = conn.execute(
            "SELECT id, row_count_raw FROM datasets WHERE status = 'ready' "
            "ORDER BY row_count_raw DESC"
        ).fetchall()
    finally:
        conn.close()

    match = next((r for r in rows if r[1] == TOTAL_ROWS), None)
    if match is None:
        pytest.skip(f"no ready dataset with {TOTAL_ROWS:,} rows in {catalog_path}")

    path = live.datasets_dir / f"{match[0]}.duckdb"
    if not path.exists():
        pytest.skip(f"dataset file missing: {path}")
    conn = _open(path)
    yield conn
    conn.close()


def _open(path):
    """Read-only, and skipped rather than failed when the running server holds the file.

    DuckDB allows one writer per file and will not open it even read-only while another
    process has it open read-write, so a developer with the app running would otherwise
    see these as failures with nothing wrong.
    """
    import duckdb

    try:
        return duckdb.connect(str(path), read_only=True)
    except duckdb.IOException as exc:
        if "another process" in str(exc) or "already open" in str(exc):
            pytest.skip(f"{path.name} is held by the running server - stop the backend first")
        raise


def test_the_row_count_is_what_the_audit_found(real):
    """The number everything else is a share of. If this moves, either the file changed or
    the loader started dropping or duplicating rows.
    """
    assert real.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0] == TOTAL_ROWS


def test_the_marque_count_is_stable(real):
    """Counted with a prefix match, because the manufacturer column pairs the marque with
    a country and one country's name ends in this marque's name. A `contains` match here
    returns 45,462 rows too many - the exact bug this figure was pinned to catch.
    """
    got = real.execute(
        "SELECT COUNT(*) FROM raw_data WHERE tozeret_nm LIKE 'קיה%'"
    ).fetchone()[0]
    assert got == KIA_ROWS


def test_a_two_column_intersection_is_stable(real):
    got = real.execute(
        "SELECT COUNT(*) FROM raw_data "
        "WHERE tozeret_nm LIKE 'קיה%' AND sug_delek_nm = 'בנזין'"
    ).fetchone()[0]
    assert got == KIA_PETROL_ROWS


def test_the_intersection_is_a_subset_of_the_marque(real):
    """A sanity relation the two constants must satisfy, independent of their values."""
    assert KIA_PETROL_ROWS < KIA_ROWS < TOTAL_ROWS


def test_identifiers_are_still_text_with_their_padding(real):
    """At this scale a numeric inference would be silent: the column would still be full
    of plausible numbers, just with several hundred thousand identifiers shortened.
    """
    kind = real.execute("DESCRIBE raw_data").fetchall()
    types = {r[0]: r[1] for r in kind}
    assert all(t == "VARCHAR" for t in types.values()), types

    padded = real.execute(
        "SELECT COUNT(*) FROM raw_data WHERE mispar_rechev LIKE '0%'"
    ).fetchone()[0]
    assert padded > 0, "no zero-padded identifiers left - padding has been lost"


def test_the_computed_csv_size_matches_the_measured_export(real):
    """The 739 MB write this arithmetic replaced.

    The figure on the right was measured on disk, from a real export of the cleaned table
    - 22 columns, one having been dropped, which is why it is smaller than the raw table's
    23. This is the one test proving the calculation is right at full scale, on real
    Hebrew text, and against a number the code had no part in producing.
    """
    from app.services import cleaning

    if not real.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'cleaned_data'"
    ).fetchone()[0]:
        pytest.skip("no cleaned_data table - the measured figure is for the cleaned export")

    columns = [r[0] for r in real.execute("DESCRIBE cleaned_data").fetchall()]
    assert len(columns) == 22, f"the measured figure is for 22 columns, found {len(columns)}"
    assert cleaning.csv_byte_size(real, "cleaned_data", columns) == CLEANED_CSV_BYTES


def test_a_hebrew_column_costs_far_more_bytes_than_characters(real):
    """Why strlen() and not length().

    The manufacturer column is almost entirely Hebrew, where every character is two bytes
    in UTF-8, so its byte length is close to double its character length. Asserted as a
    floor rather than an exact figure - it is a property of the content, not a constant -
    but a wide margin above 1.0, because that is the whole point: using length() here
    understated the export size by 13% across the file.
    """
    bytes_, chars = real.execute(
        "SELECT SUM(strlen(coalesce(tozeret_nm, ''))), SUM(length(coalesce(tozeret_nm, ''))) "
        "FROM raw_data"
    ).fetchone()
    assert bytes_ > chars
    assert 1.5 < bytes_ / chars <= 2.0, f"ratio {bytes_ / chars:.4f}"
