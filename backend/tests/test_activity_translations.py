"""Every action the backend records must have a label in every language.

The activity screen translates an action by its key - `admin.actions.${action}` - so an
action nobody translated does not fall back to anything readable. It renders the key
itself, in English, in the middle of an Arabic log: `dataset.renamed` sat there for
three releases next to neighbours that read properly, because nothing connected the
place actions are written to the place they are named.

This is that connection. It is a backend test reading the frontend's locale files
because the list it has to check against only exists here.
"""

import ast
import io
import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
LOCALES = BACKEND.parent / "frontend" / "src" / "i18n"
LANGUAGES = ("ar", "en", "he")


def _string_literals(node: ast.AST) -> set[str]:
    """The strings a value can actually take.

    Handles the conditional form users.py uses - `action = "a" if changed else "b"` -
    by taking both branches and not the test, which would otherwise drag in whatever
    the condition compares against.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _string_literals(node.body) | _string_literals(node.orelse)
    return set()


def logged_actions() -> set[str]:
    """Every action name reaching log_activity, read from the source."""
    found: set[str] = set()
    for path in (BACKEND / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name == "log_activity" and len(node.args) >= 2:
                    found |= _string_literals(node.args[1])
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "action":
                        found |= _string_literals(node.value)
    return found


def action_labels(language: str) -> dict:
    data = json.load(io.open(LOCALES / f"{language}.json", encoding="utf-8"))
    return data["admin"]["actions"]


def test_the_locale_files_are_where_this_expects():
    assert LOCALES.is_dir(), f"no locale directory at {LOCALES}"


def test_the_scan_finds_the_actions_it_should():
    """A guard on the guard. If the scan silently stopped finding call sites it would
    pass by knowing nothing, so a few actions from different modules are named here."""
    found = logged_actions()
    assert len(found) >= 20, found
    for expected in (
        "auth.login",              # a plain literal argument
        "user.updated",            # assigned to a variable first
        "user.password_reset",     # the other branch of that same conditional
        "dataset.renamed",
        "housekeeping.swept",
    ):
        assert expected in found, f"the scan missed {expected}"
    assert "password_hash" not in found, "the conditional's test leaked into the results"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_logged_action_has_a_label(language):
    labels = action_labels(language)
    missing = sorted(a for a in logged_actions() if a not in labels)
    assert not missing, (
        f"{language}.json has no admin.actions entry for: {', '.join(missing)} - "
        "the activity log will show the key instead"
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_label_is_left_blank(language):
    labels = action_labels(language)
    blank = sorted(k for k, v in labels.items() if not str(v).strip())
    assert not blank, f"{language}.json has empty labels for: {', '.join(blank)}"


def test_the_languages_agree_on_which_actions_they_name():
    """A label added to one file and forgotten in the others is the same bug one
    language at a time."""
    sets = {lang: set(action_labels(lang)) for lang in LANGUAGES}
    everything = set().union(*sets.values())
    for lang, present in sets.items():
        assert not (everything - present), (
            f"{lang}.json is missing: {', '.join(sorted(everything - present))}"
        )


def test_no_label_describes_an_action_that_is_never_recorded():
    """The other direction, kept as a warning about dead entries rather than a failure:
    a label for an action that no longer exists is clutter, not a defect."""
    found = logged_actions()
    orphans = sorted(k for k in action_labels("ar") if k not in found)
    assert not orphans, f"labels with no matching action: {', '.join(orphans)}"


# ---- the detail line under the action -------------------------------------------------

def detail_codes() -> set[str]:
    """Every detail_code passed to log_activity, read from the source.

    Several call sites choose between two codes on the spot - a backup taken with or
    without the originals, a schedule turned off or set - so both branches count.
    """
    found: set[str] = set()
    for path in (BACKEND / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # detail_code="..." passed straight in, either branch of a conditional
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name == "log_activity":
                    for keyword in node.keywords:
                        if keyword.arg == "detail_code":
                            found |= _string_literals(keyword.value)
            # the housekeeping call settles on `code` over an if/elif first
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "code":
                        found |= _string_literals(node.value)
    return found


# i18next appends one of these to a key that varies with a number. Arabic uses all six,
# Hebrew three, English two - so the three files legitimately hold different key counts
# for the same sentence, and every comparison here works on the base name.
PLURAL_SUFFIXES = ("_zero", "_one", "_two", "_few", "_many", "_other")


def base_key(key: str) -> str:
    for suffix in PLURAL_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return key


def detail_messages(language: str) -> dict:
    data = json.load(io.open(LOCALES / f"{language}.json", encoding="utf-8"))
    return data["admin"].get("details", {})


def detail_base_names(language: str) -> set[str]:
    return {base_key(k) for k in detail_messages(language)}


def test_the_scan_finds_the_detail_codes():
    codes = detail_codes()
    assert len(codes) >= 15, codes
    for expected in ("rows_change", "import_config", "was_named", "schedule_off", "retention_both"):
        assert expected in codes, f"the scan missed {expected}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_detail_code_has_a_sentence(language):
    names = detail_base_names(language)
    missing = sorted(c for c in detail_codes() if c not in names)
    assert not missing, (
        f"{language}.json has no admin.details entry for: {', '.join(missing)} - "
        "the log will fall back to the English sentence"
    )


def test_the_languages_agree_on_which_details_they_name():
    sets = {lang: detail_base_names(lang) for lang in LANGUAGES}
    everything = set().union(*sets.values())
    for lang, present in sets.items():
        assert not (everything - present), (
            f"{lang}.json is missing: {', '.join(sorted(everything - present))}"
        )


def _placeholders_by_base(language: str) -> dict[str, set[str]]:
    """What each sentence interpolates, pooled over its plural forms.

    Pooled because the forms legitimately differ: Arabic's "one" reads "صلاحية واحدة"
    and carries no number at all, while its "few" reads "{{count}} صلاحيات".
    """
    out: dict[str, set[str]] = {}
    for key, text in detail_messages(language).items():
        out.setdefault(base_key(key), set()).update(re.findall(r"{{(\w+)}}", text))
    return out


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_placeholders_match_across_languages(language):
    """A translation that drops a placeholder silently loses the value it carried, and
    one that invents a placeholder renders it raw.

    `count` is excluded because a plural form may spell the number out instead of
    printing it; the form-by-form check below covers what it leaves.
    """
    reference = _placeholders_by_base("en")
    for code, actual in _placeholders_by_base(language).items():
        expected = reference.get(code, set()) - {"count"}
        assert (actual - {"count"}) == expected, (
            f"{language}.json '{code}' uses {sorted(actual)}, English uses "
            f"{sorted(reference.get(code, set()))}"
        )


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_plural_sentence_still_prints_its_number_where_english_does(language):
    """The form used for larger counts has to show the figure. Dropping {{count}} from
    "_other" turns "11 files" into "files"."""
    english = detail_messages("en")
    for key, text in detail_messages(language).items():
        if not key.endswith("_other"):
            continue
        reference = english.get(key) or english.get(base_key(key)) or ""
        if "{{count}}" in reference:
            assert "{{count}}" in text, f"{language}.json '{key}' lost its number"


def test_the_field_names_inside_a_change_list_are_named():
    """`changed_fields` interpolates a list of column names, each shown to the reader."""
    for language in LANGUAGES:
        data = json.load(io.open(LOCALES / f"{language}.json", encoding="utf-8"))
        fields = data["admin"].get("fields", {})
        for expected in ("role", "status", "permissions", "password_hash"):
            assert expected in fields, f"{language}.json has no admin.fields.{expected}"
