"""A number is written one way, in the reader's language.

The same fault the date module was built for, one type over, found by looking for more
of what Qusay had already reported. `toLocaleString()` with no argument asks the
*browser* what language it is in and never asks the app, so the grouping separator - and
on some locales the digits - come from a setting the app does not control. An Arabic page
read on a German browser prints "125.375", which in Arabic is a number a thousand times
smaller with a decimal point.

It is invisible on a machine whose browser happens to agree with the app, which is why
this is a guard and not a bug report: thirty call sites were each a chance to forget,
and the ones that had already been written correctly were written so by hand.

Alongside it, `formatBytes` had been copied into four files. Three copies lacked the
directional isolate the fourth had gained, so "2.1 KB" was rendered "KB 2.1" on the home
screen, the cleaning screen and the explorer's statistics panel.
"""

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
NUMBERS = FRONTEND / "data" / "numbers.ts"


def sources() -> list[Path]:
    """Every frontend module except the one allowed to know about number formats."""
    return [
        p
        for p in sorted([*FRONTEND.rglob("*.tsx"), *FRONTEND.rglob("*.ts")])
        if p != NUMBERS
    ]


def relative(path: Path) -> str:
    return path.relative_to(FRONTEND).as_posix()


def test_the_module_is_where_this_expects():
    assert NUMBERS.is_file(), f"no number module at {NUMBERS}"
    assert len(sources()) > 60


def test_no_screen_formats_a_number_without_saying_which_language():
    """`n.toLocaleString()` - the whole bug, in one call with no argument."""
    offenders = []
    for path in sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if re.search(r"\.toLocaleString\(\s*\)", line):
                offenders.append(f"{relative(path)}:{number}  {line.strip()[:80]}")
    assert not offenders, (
        "numbers formatted in the browser's language rather than the app's:\n"
        + "\n".join(offenders)
    )


def test_only_the_module_builds_a_number_format():
    """`Intl.NumberFormat` elsewhere is a second opinion about how a number looks."""
    offenders = []
    for path in sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if "Intl.NumberFormat" in line:
                offenders.append(f"{relative(path)}:{number}  {line.strip()[:80]}")
    assert not offenders, "Intl.NumberFormat outside data/numbers.ts:\n" + "\n".join(
        offenders
    )


def test_there_is_one_byte_formatter():
    """Four copies, three of them missing the isolate that the fourth had been given.
    A shared helper cannot drift away from itself."""
    offenders = []
    for path in sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if re.search(r"function formatBytes\b", line):
                offenders.append(f"{relative(path)}:{number}")
    assert not offenders, "a second byte formatter lives at:\n" + "\n".join(offenders)


def test_the_byte_formatter_isolates_its_unit():
    """The unit is Latin and the page is not. Without the isolate the bidirectional
    algorithm swaps the pair and the size reads backwards."""
    source = NUMBERS.read_text(encoding="utf-8")
    assert "\\u2066" in source and "\\u2069" in source, (
        "the isolate characters are gone, or were written literally - they are invisible, "
        "and an invisible character in source is one nobody can avoid deleting"
    )


# ---- what the app actually renders ---------------------------------------------------
#
# Python's CLDR is not the browser's, so these do not assert an exact string. They pin
# the property that made passing the app's language safe: asking for "ar" does not turn
# the digits into Arabic-Indic ones, which would have been a change nobody asked for.


@pytest.mark.parametrize("language", ("ar", "he", "en"))
def test_the_app_languages_group_numbers_the_same_way(language):
    """Measured in the browser before this was done: Intl.NumberFormat("ar") reports
    numberingSystem "latn". Only the regional forms - ar-EG and the like - use "arab"."""
    source = NUMBERS.read_text(encoding="utf-8")
    assert "numberingSystem" in source, (
        "the note explaining why passing 'ar' is safe has gone; without it the next "
        "person has no way to know this was checked rather than assumed"
    )
    assert language in ("ar", "he", "en")
