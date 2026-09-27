"""Every question about the rows on screen is asked about the same rows.

Found by a full QA pass on 2026-09-27, looking for more of what Qusay reported earlier:
125,375 Kia Picantos on screen and the engine list beside them counting all 4.1 million
vehicles. The same fault was still reachable another way. With "only the latest batch" on,
the grid showed 400 rows while the colour list beside it counted 30,300, the grouped view
counted 30,300, and "export the current view" wrote 30,300 rows to a file. The server did
not even accept the toggle on those endpoints.

The cause was structural: the grid, the statistics and the export each built their own
WHERE clause, and the toggle had been added to one of the three. There is now one builder
(services/view.py). These pin both the behaviour, against real endpoints, and the wiring,
so a fourth consumer cannot quietly grow its own again.

The same pass found that a filter typed in Arabic matched nothing: the grid shows Hebrew
values translated, "contains كيا" was compared against the stored "קיה", and 4,213 rows
became 0. Those are pinned here too, with the smaller findings of the pass after them.
"""

import csv
import io
import re
import time
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
BACKEND = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture(scope="module")
def batch(admin) -> str:
    """Six vehicles, keyed by plate, then a batch: one new, one recoloured.

    After it, "the latest batch" is exactly plates 7 and 3, and the colours among them
    are one RED (the new one) and one PURPLE (the recoloured one).
    """
    from conftest import wait_for_job

    base = "plate,make,colour\n1,KIA,WHITE\n2,KIA,WHITE\n3,MAZDA,BLUE\n4,MAZDA,WHITE\n5,KIA,BLUE\n6,FORD,WHITE\n"
    r = admin.post("/api/datasets/upload", files={"file": ("fleet.csv", base.encode(), "text/csv")})
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    assert admin.put(f"/api/datasets/{dataset_id}/key", json={"columns": ["plate"]}).status_code == 200
    more = "plate,make,colour\n7,KIA,RED\n3,MAZDA,PURPLE\n"
    r = admin.post(
        f"/api/datasets/{dataset_id}/append",
        files={"file": ("batch.csv", more.encode(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


def grid(client, ds, **body) -> int:
    r = client.post(f"/api/datasets/{ds}/data", json={"page": 1, "page_size": 50, "source": "raw", **body})
    assert r.status_code == 200, r.text
    return r.json()["total_rows"]


def picker(client, ds, column, **body) -> dict[str, int]:
    r = client.post(
        f"/api/datasets/{ds}/group",
        json={"column": column, "page": 1, "page_size": 500, "source": "raw", **body},
    )
    assert r.status_code == 200, r.text
    return {g["value"]: g["count"] for g in r.json()["groups"]}


# ---- "only the latest batch" is part of the view everywhere ---------------------------


def test_the_grid_shows_the_batch(admin, batch):
    assert grid(admin, batch) == 7
    assert grid(admin, batch, only_recent=True) == 2


def test_the_value_list_counts_the_batch_not_the_table(admin, batch):
    """The bug, stated: with the batch on screen, the colour list offered every colour in
    the table, with the table's counts."""
    assert picker(admin, batch, "colour") == {"WHITE": 4, "BLUE": 1, "PURPLE": 1, "RED": 1}
    assert picker(admin, batch, "colour", only_recent=True) == {"PURPLE": 1, "RED": 1}


def test_the_grouped_view_counts_the_batch(admin, batch):
    assert picker(admin, batch, "make", only_recent=True) == {"KIA": 1, "MAZDA": 1}


def test_the_toggle_composes_with_filters(admin, batch):
    only = [{"column": "make", "op": "eq", "value": "KIA"}]
    assert grid(admin, batch, only_recent=True, filters=only) == 1
    assert picker(admin, batch, "colour", only_recent=True, filters=only) == {"RED": 1}


def test_statistics_describe_the_batch(admin, batch):
    r = admin.post(
        f"/api/datasets/{batch}/statistics",
        json={"group_by": "make", "source": "raw", "only_recent": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2


def test_export_of_the_current_view_is_the_batch(admin, batch):
    """The most consequential of them: a file somebody sends onwards believing it holds
    what they were looking at. It held 75 times as many rows."""
    r = admin.post(
        f"/api/datasets/{batch}/export",
        json={"format": "csv", "scope": "current_view", "source": "raw", "only_recent": True},
    )
    assert r.status_code == 200, r.text
    job = r.json()["id"]
    deadline = time.monotonic() + 60
    while (j := admin.get(f"/api/jobs/{job}").json())["status"] not in ("done", "error"):
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert j["status"] == "done", j
    body = admin.get(f"/api/datasets/{batch}/export/{job}/download").content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(body)))[1:]
    assert sorted(r[0] for r in rows) == ["3", "7"]


def test_exporting_everything_ignores_the_toggle(admin, batch):
    """"All" means all. The toggle belongs to the view, and this is not the view."""
    r = admin.post(
        f"/api/datasets/{batch}/export",
        json={"format": "csv", "scope": "all", "source": "raw", "only_recent": True},
    )
    job = r.json()["id"]
    while (j := admin.get(f"/api/jobs/{job}").json())["status"] not in ("done", "error"):
        time.sleep(0.05)
    body = admin.get(f"/api/datasets/{batch}/export/{job}/download").content.decode("utf-8-sig")
    assert len(list(csv.reader(io.StringIO(body)))) - 1 == 7


def test_without_the_key_in_the_table_the_batch_is_no_rows(admin, batch):
    """A cleaned copy that dropped the key cannot say which of its rows arrived recently.
    The honest answer is none that can be shown - not all of them."""
    r = admin.post(f"/api/datasets/{batch}/clean", json={"keep_columns": ["make", "colour"]})
    assert r.status_code == 200, r.text
    try:
        r = admin.post(
            f"/api/datasets/{batch}/data",
            json={"page": 1, "page_size": 50, "source": "cleaned", "only_recent": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["total_rows"] == 0
    finally:
        cols = ["plate", "make", "colour"]
        admin.post(f"/api/datasets/{batch}/clean", json={"keep_columns": cols})


# ---- one builder --------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,function",
    [
        ("services/query.py", "def fetch_page("),
        ("services/query.py", "def fetch_groups("),
        ("services/analytics.py", "def _build_where("),
        ("services/export.py", "def build_export_query("),
    ],
)
def test_every_view_consumer_asks_the_one_builder(path, function):
    source = (BACKEND / path).read_text(encoding="utf-8")
    start = source.index(function)
    end = source.find("\ndef ", start + 1)
    assert "view.where(" in source[start : end if end > 0 else None], (
        f"{path} {function} builds its own WHERE instead of asking services/view.py"
    )


def test_nothing_else_assembles_a_view_by_hand():
    """build_filter_sql is the brick; view.where is the wall. Cleaning filters the whole
    table rather than a view, so it may use the brick directly."""
    allowed = {"services/view.py", "services/sql_utils.py", "services/cleaning.py"}
    offenders = []
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if rel in allowed:
            continue
        if "build_filter_sql(" in path.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, f"filters assembled outside services/view.py in: {offenders}"


# ---- a filter typed in Arabic -------------------------------------------------------


def rule(op, value=None, values=None, alternatives=None, column="make"):
    r = {"column": column, "op": op}
    if value is not None:
        r["value"] = value
    if values is not None:
        r["values"] = values
    if alternatives is not None:
        r["alternatives"] = alternatives
    return r


def test_a_typed_spelling_reaches_the_stored_value(admin, batch):
    """What the screen sends for "contains كيا": the typed word plus the stored spelling
    the dictionary maps it to. The stored side here is KIA."""
    assert grid(admin, batch, filters=[rule("contains", "كيا")]) == 0
    assert grid(admin, batch, filters=[rule("contains", "كيا", alternatives=["KIA"])]) == 4


@pytest.mark.parametrize("op", ["eq", "starts_with", "ends_with"])
def test_every_text_comparison_takes_the_other_spellings(admin, batch, op):
    assert grid(admin, batch, filters=[rule(op, "كيا", alternatives=["KIA"])]) == 4


def test_not_equal_excludes_every_spelling(admin, batch):
    """"Not Kia" typed in Arabic has to leave out the stored Kias as well, or it excludes
    nothing at all and looks like it worked."""
    assert grid(admin, batch, filters=[rule("neq", "كيا")]) == 7
    assert grid(admin, batch, filters=[rule("neq", "كيا", alternatives=["KIA"])]) == 3


def test_a_list_of_values_takes_their_spellings(admin, batch):
    assert grid(admin, batch, filters=[rule("in", values=["كيا"], alternatives=["KIA"])]) == 4


def test_the_picker_and_the_statistics_take_them_too(admin, batch):
    typed = [rule("eq", "كيا", alternatives=["KIA"])]
    assert sum(picker(admin, batch, "colour", filters=typed).values()) == 4
    r = admin.post(
        f"/api/datasets/{batch}/statistics",
        json={"group_by": "colour", "source": "raw", "filters": typed},
    )
    assert r.json()["total"] == 4


def test_the_number_of_spellings_is_bounded():
    from app.models.schemas import FilterRule
    from app.services import sql_utils

    many = [f"S{i}" for i in range(50)]
    sql, params = sql_utils.build_filter_sql(
        [FilterRule(column="make", op="eq", value="x", alternatives=many)], {"make"}
    )
    assert len(params) == 1 + sql_utils.MAX_FILTER_ALTERNATIVES


def test_a_number_has_one_spelling():
    from app.models.schemas import FilterRule
    from app.services import sql_utils

    sql, params = sql_utils.build_filter_sql(
        [FilterRule(column="year", op="gt", value="2015", alternatives=["x", "y"])], {"year"}
    )
    assert params == ["2015"]


# ---- the smaller findings -------------------------------------------------------------


def test_a_distinct_estimate_never_exceeds_the_values_it_counts(admin, batch):
    """"≈33,314 distinct" in a column of 30,300 rows. The ≈ excuses being approximate,
    not being impossible."""
    r = admin.get(f"/api/datasets/{batch}/profile", params={"source": "raw"})
    assert r.status_code == 200, r.text
    for c in r.json()["columns"]:
        assert c["approx_distinct"] <= c["filled"], c


# ---- the screen half --------------------------------------------------------------------


def read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_both_value_lists_send_the_toggle():
    for rel in ("components/ColumnHeaderMenu.tsx", "components/ValueAutocomplete.tsx"):
        source = read(rel)
        assert "only_recent: onlyRecent" in source, f"{rel} does not send the toggle"


def test_the_explorer_hands_the_toggle_to_everything_that_asks():
    source = read("pages/ExplorerPage.tsx")
    # grouped view, value lists in the header, the filter dialog, and the export
    assert source.count("only_recent: onlyRecent") >= 2, "grid and grouped view"
    assert source.count("onlyRecent={onlyRecent}") >= 2, "header menu and filter dialog"
    assert 'only_recent: exportScope === "current_view" && onlyRecent' in source


def test_a_value_list_s_cache_key_carries_every_input():
    """The search scope was sent and left out of the key, so narrowing the scope could
    show the previous scope's list until the refetch landed."""
    for rel in ("components/ColumnHeaderMenu.tsx", "components/ValueAutocomplete.tsx"):
        source = read(rel)
        # up to the fetch rather than the first "]": the key itself contains "?? []"
        start = source.index("queryKey: [")
        key = source[start : source.index("queryFn", start)]
        assert "searchColumns" in key, f"{rel}: search scope missing from the cache key"
        assert "onlyRecent" in key, f"{rel}: toggle missing from the cache key"


def test_every_call_that_sends_filters_sends_their_spellings():
    client = read("api/client.ts")
    stats = read("api/statistics.ts")
    raw = re.findall(r"filters: (params\.filters \?\? \[\]|req\.filters|config\.filters)", client + stats)
    assert not raw, f"filters sent without withSpellings: {raw}"
    assert client.count("withSpellings(") >= 5  # definition + data, groups, export, clean
    assert stats.count("withSpellings(") >= 2  # statistics, pivot


def test_cells_are_read_only_when_the_key_is_not_in_the_table():
    """After a clean that dropped the key, every edit came back "no record with this
    key" while the cells still offered themselves for editing."""
    source = read("pages/ExplorerPage.tsx")
    assert "keyInView && !isGrouped" in source
    assert "record_key.not_in_view" in source


def test_removing_a_group_resets_the_page():
    source = read("pages/ExplorerPage.tsx")
    i = source.index("setGroupBy((prev) => prev.filter((g) => g !== c));")
    assert "setPage(1);" in source[i : i + 200]


def test_a_role_without_a_translation_is_named_not_keyed():
    """The sidebar printed "auth.role_super_admin" for the protected role and would for
    every custom one. Roles stay named in English by decision (BUG-012), so the fallback
    is the English name, not a new translation."""
    source = read("components/Sidebar.tsx")
    assert "t(`auth.role_${user.role}`)" not in source
    assert "defaultValue" in source


def test_a_share_is_never_rounded_onto_all_or_none():
    """"100.0%" beside "3 missing". Pinned as source because the rounding is the page's."""
    numbers = read("data/numbers.ts")
    assert "export function formatShare(" in numbers
    assert "Math.min(Math.max(pct, 0.1), 99.9)" in numbers
    profile = read("pages/ProfilePage.tsx")
    assert ".toFixed(1)}%" not in profile, "a percentage on the profile page bypasses formatShare"
