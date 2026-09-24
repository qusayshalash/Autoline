"""The values a column offers to filter by are the ones in front of you.

Qusay had the registry narrowed to 125,375 Kia Picantos and opened the engine-model
column's value list. It offered 5,924 engine models with counts in the hundreds of
thousands - the whole 4.1M-row table - so the list answered a question he had not asked
and none of its numbers matched the screen.

The list is a grouping of the current view, which is a question the group endpoint
already answers with the view's filters and search applied. What these pin is the rule
that makes it usable: filters on *other* columns narrow the list, and a filter on the
column itself does not, because a list narrowed by its own filter can only ever offer
back what is already chosen.
"""

import pytest


@pytest.fixture(scope="module")
def fleet(admin) -> str:
    """Two makes, each with its own engines, and one engine they share."""
    from conftest import wait_for_job

    rows = [
        "1,KIA,G4LA",
        "2,KIA,G4LA",
        "3,KIA,G3LA",
        "4,MAZDA,Z6",
        "5,MAZDA,Z6",
        "6,MAZDA,Z6",
        "7,KIA,SHARED",
        "8,MAZDA,SHARED",
    ]
    body = ("plate,make,engine" + chr(10) + chr(10).join(rows) + chr(10)).encode("utf-8")
    r = admin.post("/api/datasets/upload", files={"file": ("fleet.csv", body, "text/csv")})
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


def offered(client, dataset_id, column, **body) -> dict[str, int]:
    """What the value list would show for `column`: value -> count."""
    r = client.post(
        f"/api/datasets/{dataset_id}/group",
        json={"column": column, "source": "raw", "page": 1, "page_size": 500, **body},
    )
    assert r.status_code == 200, r.text
    return {g["value"]: g["count"] for g in r.json()["groups"] if g["value"]}


def test_with_nothing_filtered_every_value_is_offered(admin, fleet):
    assert offered(admin, fleet, "engine") == {"G4LA": 2, "G3LA": 1, "Z6": 3, "SHARED": 2}


def test_a_filter_on_another_column_narrows_the_list(admin, fleet):
    """The bug, stated: with the view showing only Kias, the engine list must be the
    engines Kias have - and the counts must be the ones on screen, not the table's."""
    kias = offered(
        admin, fleet, "engine", filters=[{"column": "make", "op": "eq", "value": "KIA"}]
    )
    assert kias == {"G4LA": 2, "G3LA": 1, "SHARED": 1}
    assert "Z6" not in kias, "an engine no Kia has was offered while filtered to Kias"


def test_the_shared_value_is_counted_in_the_view_not_in_the_table(admin, fleet):
    """SHARED appears twice overall and once among Kias. The number beside it has to be
    the second one, or the list is describing a table nobody is looking at."""
    assert offered(admin, fleet, "engine")["SHARED"] == 2
    kias = offered(
        admin, fleet, "engine", filters=[{"column": "make", "op": "eq", "value": "KIA"}]
    )
    assert kias["SHARED"] == 1


def test_the_search_box_narrows_it_too(admin, fleet):
    """Whatever is typed in the grid's search is part of what is on screen."""
    assert offered(admin, fleet, "engine", search="MAZDA") == {"Z6": 3, "SHARED": 1}


def test_a_filter_on_the_column_itself_is_left_out_by_the_caller(admin, fleet):
    """Not a rule the server enforces - it applies what it is given - but the reason the
    screen drops this column's own filter before asking. Sending it produces a list that
    offers back only what is already chosen, and no second value can ever be added."""
    narrowed = offered(
        admin, fleet, "engine", filters=[{"column": "engine", "op": "in", "values": ["Z6"]}]
    )
    assert narrowed == {"Z6": 3}


def test_the_count_of_distinct_values_follows_the_view(admin, fleet):
    """The "showing 500 of N" line under the list. N was the table's distinct count,
    which stayed the same however narrow the view got."""
    everything = admin.post(
        f"/api/datasets/{fleet}/group",
        json={"column": "engine", "source": "raw", "page": 1, "page_size": 500},
    ).json()
    kias = admin.post(
        f"/api/datasets/{fleet}/group",
        json={
            "column": "engine",
            "source": "raw",
            "page": 1,
            "page_size": 500,
            "filters": [{"column": "make", "op": "eq", "value": "KIA"}],
        },
    ).json()
    assert everything["total_groups"] == 4
    assert kias["total_groups"] == 3


# ---- the screen half -----------------------------------------------------------------


def test_the_menu_asks_the_endpoint_that_knows_about_filters():
    """A guard: the distinct-values endpoint takes no filters, so a menu built on it
    cannot narrow however carefully the caller passes them."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent.parent
        / "frontend"
        / "src"
        / "components"
        / "ColumnHeaderMenu.tsx"
    ).read_text(encoding="utf-8")
    assert "fetchGroups" in source
    assert "fetchDistinctValues" not in source
    # and that it drops its own column's filter before asking
    assert "filters.filter((f) => f.column !== column)" in source

# ---- the picker's own search box ------------------------------------------------------


def test_the_value_box_narrows_the_values_not_the_rows(admin, fleet):
    """Typing in the list's search box asks about this column's values. Sending it as a
    row search would ask a different question - which rows contain that text anywhere -
    and on a wide table that is almost every row."""
    assert offered(admin, fleet, "engine", value_search="G4") == {"G4LA": 2}
    assert offered(admin, fleet, "engine", value_search="G") == {"G4LA": 2, "G3LA": 1}


def test_the_two_searches_compose(admin, fleet):
    """The row search says what is on screen; the value search says what is being looked
    for in the list. Both at once is the normal case - a narrowed view, and a long list
    being searched."""
    assert offered(admin, fleet, "engine", search="KIA", value_search="G3") == {"G3LA": 1}


def test_a_typed_wildcard_is_a_character_here_too(admin, fleet):
    assert offered(admin, fleet, "engine", value_search="%") == {}


def test_the_value_box_reaches_a_translated_value(admin, fleet):
    """It goes through the same builder as every other search, so the alternatives the
    screen derives from the dictionary apply: what is typed is the translation, what is
    stored is the original."""
    assert offered(admin, fleet, "engine", value_search="motor") == {}
    assert offered(
        admin, fleet, "engine", value_search="motor", value_search_alternatives=["Z6"]
    ) == {"Z6": 3}


def test_the_suggestion_box_asks_with_the_other_conditions(admin, fleet):
    """The filter dialog, building "make = KIA and engine = ...". Offering the engines
    of every other make there means picking one and getting no rows back."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent.parent
        / "frontend"
        / "src"
        / "components"
        / "ValueAutocomplete.tsx"
    ).read_text(encoding="utf-8")
    assert "fetchGroups" in source
    assert "fetchDistinctValues" not in source

    builder = (
        Path(__file__).resolve().parent.parent.parent
        / "frontend"
        / "src"
        / "components"
        / "FilterBuilder.tsx"
    ).read_text(encoding="utf-8")
    # each rule is handed every rule but itself
    assert "filters.filter((_, other) => other !== i)" in builder
