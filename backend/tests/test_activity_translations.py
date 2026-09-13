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
