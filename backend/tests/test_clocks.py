"""Timestamp storage and transmission.

The bug these guard against was invisible for a long time, which is what makes it worth
a file of its own: values were stored as local wall-clock and rendered as local
wall-clock, so on one machine in one timezone the two errors cancelled exactly. They
stop cancelling for a viewer elsewhere, or across a daylight-saving change.
"""

from datetime import datetime, timedelta, timezone

import duckdb
import pytest
from app.db import timestamp_migration
from app.services import clocks


# ---- what goes in ------------------------------------------------------------------


def test_now_is_utc_without_a_marker(monkeypatch):
    """Naive, because DuckDB converts an aware value to local time on write; UTC,
    because that is what everything else assumes it read."""
    value = clocks.now()
    assert value.tzinfo is None
    assert abs((value - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()) < 5


def test_an_aware_value_is_converted_not_stripped(monkeypatch):
    """Stripping the marker off an aware non-UTC datetime would store the wrong instant.
    It has to be converted first."""
    aware = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    assert clocks.to_db(aware) == datetime(2026, 1, 2, 7, 0, 0)


def test_a_naive_value_is_taken_as_utc_already():
    naive = datetime(2026, 1, 2, 10, 0, 0)
    assert clocks.to_db(naive) == naive


def test_what_duckdb_stores_survives_the_round_trip(tmp_path):
    """The actual failure, reproduced: an aware datetime does not round-trip through a
    DuckDB TIMESTAMP, and a naive one does. This is why `now()` returns naive."""
    conn = duckdb.connect(str(tmp_path / "t.duckdb"))
    conn.execute("CREATE TABLE t (label VARCHAR, v TIMESTAMP)")

    instant = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    conn.execute("INSERT INTO t VALUES ('aware', ?)", [instant])
    conn.execute("INSERT INTO t VALUES ('ours', ?)", [clocks.to_db(instant)])
    stored = dict(conn.execute("SELECT label, v FROM t").fetchall())
    conn.close()

    ours = stored["ours"]
    assert ours == datetime(2026, 1, 2, 10, 0, 0), "our own writes must round-trip exactly"
    # and the naive form is what makes that true - an aware value only round-trips on a
    # machine that happens to be on UTC
    if datetime.now().astimezone().utcoffset() != timedelta(0):
        assert stored["aware"] != ours


# ---- what goes out -----------------------------------------------------------------


def test_iso_marks_the_value_as_utc():
    """The Z is the whole point: without it every browser reads the string as local
    time, and a UTC value is displayed shifted by the viewer's own offset."""
    assert clocks.iso(datetime(2026, 1, 2, 10, 0, 0)) == "2026-01-02T10:00:00Z"


def test_iso_is_not_what_str_produces():
    value = datetime(2026, 1, 2, 10, 0, 0)
    assert "Z" not in str(value)
    assert clocks.iso(value).endswith("Z")


def test_iso_passes_none_through():
    assert clocks.iso(None) is None


def test_iso_converts_an_aware_value_rather_than_relabelling_it():
    aware = datetime(2026, 1, 2, 13, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    assert clocks.iso(aware) == "2026-01-02T10:00:00Z"


# ---- the API actually emits it -----------------------------------------------------


def test_the_activity_feed_sends_instants(admin, dataset):
    """Read through the endpoint rather than the helper, so a route that still uses
    str() is caught here rather than by somebody reading a wrong time on screen."""
    items = admin.get("/api/admin/activity", params={"page_size": 5}).json()["items"]
    assert items, "the fixture should have produced activity"
    assert items[0]["at"].endswith("Z"), items[0]["at"]


def test_user_records_send_instants(admin):
    me = admin.get("/api/auth/me").json()
    assert me["created_at"].endswith("Z")


def test_dataset_records_send_instants(admin, dataset):
    row = admin.get(f"/api/datasets/{dataset}").json()
    assert row["created_at"].endswith("Z")
    assert row["updated_at"].endswith("Z")


def test_the_time_sent_is_the_time_that_just_happened(admin):
    """Ties the two halves together: what the API reports for an action taken now must
    be now, in UTC, not three hours from now."""
    before = datetime.now(timezone.utc)
    admin.get("/api/auth/me")
    items = admin.get("/api/admin/activity", params={"page_size": 20}).json()["items"]

    latest = max(
        datetime.fromisoformat(i["at"].replace("Z", "+00:00")) for i in items
    )
    assert abs((latest - before).total_seconds()) < 3600, (
        f"the newest activity is at {latest}, but it is now {before}"
    )


# ---- the migration -----------------------------------------------------------------


class _Settings(dict):
    """Stands in for the app_settings table."""

    def get_setting(self, key, default=None):
        return self.get(key, default)

    def set_setting(self, key, value):
        self[key] = value


@pytest.fixture
def legacy(tmp_path):
    """A catalog holding timestamps the old way: local wall-clock, unmarked."""
    conn = duckdb.connect(str(tmp_path / "legacy.duckdb"))
    conn.execute("CREATE TABLE activity_log (id VARCHAR, occurred_at TIMESTAMP)")
    local_wall_clock = datetime.now().replace(microsecond=0)
    conn.execute("INSERT INTO activity_log VALUES ('a', ?)", [local_wall_clock])
    return conn, local_wall_clock


def test_the_migration_shifts_by_the_local_offset(legacy):
    conn, written = legacy
    settings = _Settings()

    result = timestamp_migration.run(conn, settings.get_setting, settings.set_setting)
    stored = conn.execute("SELECT occurred_at FROM activity_log").fetchone()[0]

    if datetime.now().astimezone().utcoffset() == timedelta(0):
        assert result["applied"] is False
        assert stored == written
    else:
        assert result["applied"] is True
        assert stored == clocks.local_naive_to_utc(written)
        assert stored != written


def test_the_migration_refuses_to_run_twice(legacy):
    """The dangerous failure: a second pass would shift everything again, and nothing
    afterwards could tell that it had."""
    conn, _ = legacy
    settings = _Settings()

    timestamp_migration.run(conn, settings.get_setting, settings.set_setting)
    after_first = conn.execute("SELECT occurred_at FROM activity_log").fetchone()[0]

    second = timestamp_migration.run(conn, settings.get_setting, settings.set_setting)
    assert second["applied"] is False
    assert conn.execute("SELECT occurred_at FROM activity_log").fetchone()[0] == after_first


def test_the_migration_records_that_it_ran(legacy):
    conn, _ = legacy
    settings = _Settings()
    timestamp_migration.run(conn, settings.get_setting, settings.set_setting)
    assert timestamp_migration.MARKER in settings


def test_the_migration_ignores_tables_that_are_not_there(tmp_path):
    """It runs against catalogs of several ages; a table added later must not break it."""
    conn = duckdb.connect(str(tmp_path / "sparse.duckdb"))
    conn.execute("CREATE TABLE datasets (id VARCHAR, created_at TIMESTAMP)")
    settings = _Settings()
    timestamp_migration.run(conn, settings.get_setting, settings.set_setting)  # must not raise


def test_the_migration_leaves_nulls_alone(tmp_path):
    conn = duckdb.connect(str(tmp_path / "nulls.duckdb"))
    conn.execute("CREATE TABLE users (id VARCHAR, created_at TIMESTAMP, last_login_at TIMESTAMP)")
    conn.execute("INSERT INTO users VALUES ('u', ?, NULL)", [datetime.now()])
    settings = _Settings()
    timestamp_migration.run(conn, settings.get_setting, settings.set_setting)
    assert conn.execute("SELECT last_login_at FROM users").fetchone()[0] is None
