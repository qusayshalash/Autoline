"""Ordering a number column by value rather than by spelling.

Every column of an imported table is stored as text, so `ORDER BY "price"` compares
strings and puts 100446 before 10099. The failure is invisible wherever the values are
the same width - which is why the fixture here deliberately mixes widths, and why one
of the tests pins the equal-width case that used to look like proof the sort worked.
"""

import csv

import pytest
from conftest import wait_for_job

# price:  two to six digits, so text order and numeric order disagree
# year:   four digits throughout, so they agree - the case that hid the bug
# code:   zero-padded, must keep sorting as written
# city:   text
# mixed:  numbers with one stray word in it
ROWS = [
    # code,      city,        price,    year,   mixed
    ["00000001", "رام الله", "99", "2015", "10"],
    ["00000002", "نابلس", "100446", "2020", "9"],
    ["00000003", "غزة", "10099", "1998", "1000"],
    ["00000004", "الخليل", "7300", "2024", "abc"],
    ["00000005", "جنين", "850", "2001", "20"],
    ["00000006", "بيت لحم", "250000", "2019", "3"],
    ["00000007", "رام الله", "5", "2007", ""],
    ["00000008", "نابلس", "64000", "2011", "7"],
    ["00000009", "غزة", "", "2022", "70"],
    ["00000010", "الخليل", "1200", "1995", "700"],
]
HEADER = ["code", "city", "price", "year", "mixed"]


@pytest.fixture(scope="module")
def sortable(admin, tmp_path_factory) -> str:
    """A small dataset imported through the real endpoints, like every other fixture."""
    path = tmp_path_factory.mktemp("numeric-sort") / "sortable.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(ROWS)

    with open(path, "rb") as f:
        r = admin.post(
            "/api/datasets/upload", files={"file": ("sortable.csv", f, "text/csv")}
        )
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]

    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert r.status_code == 200, r.text
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    return dataset_id


def column(admin, dataset_id: str, name: str, **body) -> list[str]:
    body.setdefault("page_size", 100)
    r = admin.post(f"/api/datasets/{dataset_id}/data", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    i = data["columns"].index(name)
    return [row[i] for row in data["rows"]]


def kinds(admin, dataset_id: str) -> dict[str, str]:
    r = admin.get(f"/api/datasets/{dataset_id}/columns")
    assert r.status_code == 200, r.text
    return {c["name"]: c["kind"] for c in r.json()["columns"]}


# ---- what the columns are taken to be ------------------------------------------------

def test_the_fixture_classifies_the_way_the_tests_assume(admin, sortable):
    """If this drifts, the sorting tests below stop testing what they claim to."""
    k = kinds(admin, sortable)
    assert k["price"] == "number"
    assert k["year"] == "number"
    assert k["code"] != "number"   # leading zeros keep it text
    assert k["city"] != "number"
    assert k["mixed"] != "number"  # one stray word disqualifies the whole column


# ---- the defect ----------------------------------------------------------------------

def test_a_number_column_sorts_by_value_not_by_spelling(admin, sortable):
    got = [v for v in column(admin, sortable, "price", sort_by="price", sort_dir="asc") if v]
    assert [int(v) for v in got] == sorted(int(v) for v in got)
    # the specific pair that made this visible: as text, 100446 sorts before 10099
    assert got.index("10099") < got.index("100446")


def test_descending_is_the_mirror_of_ascending(admin, sortable):
    asc = [v for v in column(admin, sortable, "price", sort_by="price", sort_dir="asc") if v]
    desc = [v for v in column(admin, sortable, "price", sort_by="price", sort_dir="desc") if v]
    assert desc == list(reversed(asc))


def test_the_equal_width_column_that_hid_the_bug_is_still_right(admin, sortable):
    """Four-digit years sort correctly either way. Kept so a future change that breaks
    numeric ordering cannot be waved through because "the year column looks fine"."""
    got = column(admin, sortable, "year", sort_by="year", sort_dir="asc")
    assert [int(v) for v in got] == sorted(int(v) for v in got)


# ---- what must not change ---------------------------------------------------------------

def test_a_zero_padded_column_still_sorts_as_written(admin, sortable):
    """Read as numbers these are 1..10; the padding exists so they sort as text."""
    got = column(admin, sortable, "code", sort_by="code", sort_dir="asc")
    assert got == sorted(got)
    assert got[0] == "00000001"


def test_a_text_column_still_sorts_as_text(admin, sortable):
    got = column(admin, sortable, "city", sort_by="city", sort_dir="asc")
    assert got == sorted(got)


def test_a_column_with_one_stray_word_keeps_text_ordering(admin, sortable):
    """Not ideal, but coherent: the grid labels this column text, so it sorts as text.
    Ordering and the column's stated kind agree, which is the property that matters."""
    assert kinds(admin, sortable)["mixed"] != "number"
    got = column(admin, sortable, "mixed", sort_by="mixed", sort_dir="asc")
    present = [v for v in got if v is not None]
    assert present == sorted(present)
    # read as text, "1000" sorts before "20" - which is the point being pinned
    assert present.index("1000") < present.index("20")


# ---- blanks ------------------------------------------------------------------------------

def test_blank_numbers_go_last_whichever_way_the_column_is_sorted(admin, sortable):
    """Otherwise sorting a column descending opens on a page of empty cells."""
    for direction in ("asc", "desc"):
        got = column(admin, sortable, "price", sort_by="price", sort_dir=direction)
        filled = [i for i, v in enumerate(got) if v]
        blanks = [i for i, v in enumerate(got) if not v]
        assert blanks, "the fixture must contain a blank price"
        assert min(blanks) > max(filled), direction


# ---- paging -------------------------------------------------------------------------------

def test_paging_a_sorted_number_column_neither_repeats_nor_skips(admin, sortable):
    """A sort with no tiebreak can reorder equal rows between requests, which shows up as
    a row appearing on two pages and another appearing on none."""
    seen: list[str] = []
    for page_no in (1, 2, 3, 4):
        seen.extend(column(admin, sortable, "code", page=page_no, page_size=3,
                           sort_by="price", sort_dir="asc"))
    assert len(seen) == len(ROWS)
    assert len(set(seen)) == len(ROWS)


# ---- the same rule in exports ----------------------------------------------------------------

def test_an_exported_view_is_ordered_the_same_way_as_the_screen(admin, sortable):
    """The export builds its own query. If only the grid were fixed, the file people
    actually send on would still be in the wrong order."""
    r = admin.post(
        f"/api/datasets/{sortable}/export",
        json={"format": "csv", "scope": "current_view", "sort_by": "price", "sort_dir": "asc"},
    )
    assert r.status_code == 200, r.text
    job = wait_for_job(admin, r.json()["id"])
    assert job["status"] == "done", job

    r = admin.get(f"/api/datasets/{sortable}/export/{job['id']}/download")
    assert r.status_code == 200, r.text
    rows = list(csv.DictReader(r.text.splitlines()))
    prices = [row["price"] for row in rows if row["price"]]
    assert [int(v) for v in prices] == sorted(int(v) for v in prices)


# ---- ordering agrees with filtering -------------------------------------------------------------

def test_an_unknown_sort_column_is_still_refused_cleanly(admin, sortable):
    """Deciding whether to cast means asking the table about the column, which is a
    query. Asked about a name that is not there it would fail inside DuckDB and surface
    as a 500, so the name is checked against the column list first."""
    for body in [
        {"sort_by": "no_such_column"},
        {"sort_by": 'price"; DROP TABLE raw_data--'},
    ]:
        r = admin.post(f"/api/datasets/{sortable}/data", json=body)
        assert r.status_code == 400, (body, r.status_code, r.text)

    # An export is queued before it is built, so the same bad name surfaces as a failed
    # job rather than a refused request - the point here is that it fails with a reason
    # instead of taking the worker down.
    r = admin.post(
        f"/api/datasets/{sortable}/export",
        json={"format": "csv", "scope": "current_view", "sort_by": "no_such_column"},
    )
    assert r.status_code == 200, r.text
    job = wait_for_job(admin, r.json()["id"])
    assert job["status"] == "error", job
    assert "no_such_column" in (job["error_message"] or "")

    # and the table is still there after the injection attempt
    r = admin.post(f"/api/datasets/{sortable}/data", json={"page_size": 1})
    assert r.status_code == 200
    assert r.json()["total_rows"] == len(ROWS)


def test_ordering_and_filtering_agree_about_what_the_column_holds(admin, sortable):
    """Numeric filters already cast with TRY_CAST. The bug was that ordering did not, so
    a column could be filtered as a number and sorted as a string in the same view."""
    r = admin.post(
        f"/api/datasets/{sortable}/data",
        json={"page_size": 100, "sort_by": "price", "sort_dir": "asc",
              "filters": [{"column": "price", "op": "gte", "value": 1000}]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    i = data["columns"].index("price")
    prices = [int(row[i]) for row in data["rows"]]

    assert prices == sorted(prices)
    assert all(p >= 1000 for p in prices)
    assert prices == [1200, 7300, 10099, 64000, 100446, 250000]
