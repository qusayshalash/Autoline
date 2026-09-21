"""Searching for a value in the language it is shown in.

The grid translates a column's Hebrew values where the dictionary can read them, and then
somebody reads the translation, types it into the search box, and gets nothing. Nothing is
the worst available answer: it does not read as "the search speaks a different language
than the table", it reads as "this data is not here".

The server does not translate. The screen that did the translating sends the original
along with the typed term, and the search looks for either. So the two halves are tested
apart: that the query really does look for every spelling it is given, and that the client
really does send them.
"""

import re
from pathlib import Path

import pytest
from app.services import sql_utils

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"

WHITE_HE = "לבן"
BLACK_HE = "שחור"


# ---- the query half ------------------------------------------------------------------


def placeholders(sql: str) -> int:
    return sql.count("?")


def test_one_term_is_unchanged():
    """The shape everything else was built on: one pattern per searched column."""
    sql, params = sql_utils.build_search_sql("kia", ["make", "model"])
    assert placeholders(sql) == len(params) == 2


def test_an_alternative_is_looked_for_as_well():
    sql, params = sql_utils.build_search_sql("white", ["colour"], [WHITE_HE])
    assert placeholders(sql) == len(params) == 2
    assert params == ["%white%", "%" + WHITE_HE + "%"]


def test_every_column_is_searched_for_every_term():
    """The bound parameters have to line up with the placeholders, in order. Getting the
    nesting backwards produces valid SQL that searches the wrong pairs, which no error
    would ever report."""
    sql, params = sql_utils.build_search_sql("white", ["a", "b", "c"], [WHITE_HE, BLACK_HE])
    assert placeholders(sql) == len(params) == 9
    assert params == ["%white%", "%" + WHITE_HE + "%", "%" + BLACK_HE + "%"] * 3


def test_a_repeated_alternative_is_not_searched_twice():
    _, params = sql_utils.build_search_sql("white", ["colour"], ["white", WHITE_HE, WHITE_HE])
    assert params == ["%white%", "%" + WHITE_HE + "%"]


def test_blank_alternatives_are_dropped():
    _, params = sql_utils.build_search_sql("kia", ["make"], ["", "   ", None])
    assert params == ["%kia%"]


def test_the_number_of_terms_is_capped():
    """Each term multiplies the OR chain by the columns searched. A dictionary offering a
    dozen readings of one word is guessing, and the cost lands on every row."""
    many = ["t%d" % i for i in range(40)]
    _, params = sql_utils.build_search_sql("x", ["a"], many)
    assert len(params) == sql_utils.MAX_SEARCH_TERMS


def test_an_alternative_is_escaped_like_the_search_is():
    """A wildcard reaching the pattern through the back door would match every row while
    looking like a search that simply found a lot."""
    _, params = sql_utils.build_search_sql("x", ["a"], ["100%"])
    assert params[1] == "%100" + chr(92) + "%%"


def test_no_terms_at_all_matches_nothing():
    sql, params = sql_utils.build_search_sql("", ["a"], [])
    assert sql == "FALSE" and params == []


# ---- through the API -----------------------------------------------------------------


@pytest.fixture(scope="module")
def bilingual(admin) -> str:
    """A dataset whose colour column is Hebrew, as the real registry's is."""
    from conftest import wait_for_job

    rows = [
        "1000001,KIA," + WHITE_HE,
        "1000002,MAZDA," + BLACK_HE,
        "1000003,KIA," + WHITE_HE,
    ]
    body = ("plate,make,colour" + chr(10) + chr(10).join(rows) + chr(10)).encode("utf-8")
    r = admin.post("/api/datasets/upload", files={"file": ("bilingual.csv", body, "text/csv")})
    assert r.status_code == 200, r.text
    dataset_id = r.json()["dataset_id"]
    r = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"
    yield dataset_id
    admin.delete(f"/api/datasets/{dataset_id}")


def page(client, dataset_id, **body):
    r = client.post(
        f"/api/datasets/{dataset_id}/data",
        json={"source": "raw", "page": 1, "page_size": 50, **body},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_the_translated_term_alone_finds_nothing(admin, bilingual):
    """Stated first, so the next test is not mistaken for the search working by accident."""
    assert page(admin, bilingual, search="white")["total_rows"] == 0


def test_the_translated_term_finds_the_rows_when_the_original_comes_with_it(admin, bilingual):
    body = page(admin, bilingual, search="white", search_alternatives=[WHITE_HE])
    assert body["total_rows"] == 2
    assert all(WHITE_HE in row for row in body["rows"])


def test_an_alternative_does_not_widen_a_search_that_already_matched(admin, bilingual):
    """The OR is between spellings of one search, not between two searches."""
    assert page(admin, bilingual, search="KIA", search_alternatives=[WHITE_HE])["total_rows"] == 2


def test_filters_still_narrow_a_search_that_used_an_alternative(admin, bilingual):
    body = page(
        admin,
        bilingual,
        search="white",
        search_alternatives=[WHITE_HE],
        filters=[{"column": "make", "op": "eq", "value": "MAZDA"}],
    )
    assert body["total_rows"] == 0


def test_suggestions_answer_the_translated_term_too(admin, bilingual):
    """The filter builder's value list. Without this, the reader types the word they were
    shown and is told the column holds no such value."""
    r = admin.get(
        f"/api/datasets/{bilingual}/data/distinct-values",
        params={"column": "colour", "source": "raw", "search": "white", "alt": [WHITE_HE]},
    )
    assert r.status_code == 200, r.text
    assert [v["value"] for v in r.json()["values"]] == [WHITE_HE]


def test_a_wildcard_in_a_suggestion_search_is_a_character(admin, bilingual):
    """distinct-values used to put the term straight into ILIKE, so a typed % listed the
    whole column while looking like a search that had matched everything."""
    r = admin.get(
        f"/api/datasets/{bilingual}/data/distinct-values",
        params={"column": "colour", "source": "raw", "search": "%"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["values"] == []


# ---- the client half -----------------------------------------------------------------
#
# The server cannot tell the difference between "this search has no translation" and "the
# screen forgot to send one". These read the client instead.

SENDS_SEARCH = re.compile(r"^\s*search: ", re.M)
SENDS_ALTERNATIVES = re.compile(r"search_alternatives: |alt: ", re.M)


@pytest.mark.parametrize("name", ("client.ts", "statistics.ts"))
def test_every_request_that_carries_a_search_carries_its_alternatives(name):
    source = (FRONTEND / "api" / name).read_text(encoding="utf-8")
    sending = len(SENDS_SEARCH.findall(source))
    alternatives = len(SENDS_ALTERNATIVES.findall(source))
    assert sending > 0, f"{name} sends no search at all - has the client moved?"
    assert alternatives >= sending, (
        f"{name} builds {sending} requests carrying a search but only {alternatives} "
        "carrying alternatives: one of them answers 'no rows' to a value on the screen"
    )


def test_the_dictionary_can_be_read_backwards():
    """The reverse lookup is what turns a translated term back into the stored one."""
    source = (FRONTEND / "data" / "valueDictionary.ts").read_text(encoding="utf-8")
    assert "export function hebrewAlternatives" in source


def test_the_repeated_query_parameter_is_serialised_as_the_server_reads_it():
    """axios sends alt[]=x by default; FastAPI reads that as a parameter of another name
    and drops it, so the suggestions would come back empty with nothing reporting why."""
    source = (FRONTEND / "api" / "client.ts").read_text(encoding="utf-8")
    assert "paramsSerializer: { indexes: null }" in source

# Every list of a column's values that a reader picks from. Showing these in one language
# while the cells behind them are in another leaves nothing to match up: the count says
# 316,253 next to a word that is nowhere on the screen.
VALUE_PICKERS = ("ColumnHeaderMenu.tsx", "ValueAutocomplete.tsx")


@pytest.mark.parametrize("name", VALUE_PICKERS)
def test_a_list_of_values_reads_in_the_same_language_as_the_column(name):
    source = (FRONTEND / "components" / name).read_text(encoding="utf-8")
    assert "translateValue" in source, (
        f"{name} lists a column's values without translating them"
    )

# ---- the dictionary itself -----------------------------------------------------------

ENTRY = re.compile(
    r"""^\s*(?P<q>['"])(?P<hebrew>.+?)(?P=q): \{ ar: "(?P<ar>[^"]*)", en: "(?P<en>[^"]*)" \},""",
    re.M,
)
HEBREW_LETTER = re.compile(r"[֐-׿]")


def entries() -> list[tuple[str, str, str]]:
    source = (FRONTEND / "data" / "valueDictionary.ts").read_text(encoding="utf-8")
    found = [(m.group("hebrew"), m.group("ar"), m.group("en")) for m in ENTRY.finditer(source)]
    assert len(found) > 200, f"only {len(found)} entries parsed - has the shape changed?"
    return found


def test_no_value_is_defined_twice():
    """A repeated key is not an error at runtime: the later one silently wins, and the
    reading somebody carefully chose is simply gone. TypeScript does object to it, which
    is exactly why this is worth a test - a dictionary edited without a build catches
    nothing."""
    seen: dict[str, int] = {}
    for hebrew, _, _ in entries():
        seen[hebrew] = seen.get(hebrew, 0) + 1
    repeated = sorted(k for k, n in seen.items() if n > 1)
    assert not repeated, "defined more than once: " + ", ".join(repeated)


def test_every_entry_says_something_in_both_languages():
    empty = [h for h, ar, en in entries() if not ar.strip() or not en.strip()]
    assert not empty, "entries with a blank reading: " + ", ".join(empty)


def test_no_entry_translates_hebrew_into_hebrew():
    """The failure a copy-paste produces, and the one that looks fine in the file: the
    value renders unchanged and reads as a word the dictionary has never heard of."""
    untranslated = [h for h, ar, en in entries() if HEBREW_LETTER.search(ar + en)]
    assert not untranslated, "still Hebrew on the other side: " + ", ".join(untranslated)
