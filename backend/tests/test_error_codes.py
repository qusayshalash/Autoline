"""Every error code the API can raise has a sentence in every language.

An ApiError exists so the interface can say the error in the reader's language. A code
with no entry in the locale files defeats the whole point quietly - the interface finds
no translation, falls back to the English detail, and looks exactly as it did before the
code was added.

The same shape as test_activity_translations: read one side out of the source, the other
out of the locale files, and refuse to let them drift.
"""

import ast
import io
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
LOCALES = BACKEND.parent / "frontend" / "src" / "i18n"
LANGUAGES = ("ar", "en", "he")


def raised_codes() -> dict[str, str]:
    """Every code passed to ApiError, mapped to the English sentence beside it."""
    found: dict[str, str] = {}
    for path in (BACKEND / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name != "ApiError" or len(node.args) < 3:
                continue
            code, detail = node.args[1], node.args[2]
            if isinstance(code, ast.Constant) and isinstance(detail, ast.Constant):
                found[code.value] = detail.value
    return found


def error_messages(language: str) -> dict:
    data = json.load(io.open(LOCALES / f"{language}.json", encoding="utf-8"))
    return data.get("errors", {})


def test_the_scan_finds_the_error_codes():
    codes = raised_codes()
    assert len(codes) >= 20, codes
    for expected in ("dataset_not_found", "forbidden", "username_taken", "too_many_attempts"):
        assert expected in codes, f"the scan missed {expected}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_raised_code_has_a_message(language):
    messages = error_messages(language)
    missing = sorted(c for c in raised_codes() if c not in messages)
    assert not missing, (
        f"{language}.json has no errors entry for: {', '.join(missing)} - "
        "the interface will fall back to the English sentence"
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_message_is_blank(language):
    blank = sorted(k for k, v in error_messages(language).items() if not str(v).strip())
    assert not blank, f"{language}.json has empty messages for: {', '.join(blank)}"


def test_no_message_describes_an_error_that_cannot_happen():
    orphans = sorted(k for k in error_messages("ar") if k not in raised_codes())
    assert not orphans, f"messages with no matching error: {', '.join(orphans)}"


def test_the_languages_agree_on_which_errors_they_name():
    sets = {lang: set(error_messages(lang)) for lang in LANGUAGES}
    everything = set().union(*sets.values())
    for lang, present in sets.items():
        assert not (everything - present), (
            f"{lang}.json is missing: {', '.join(sorted(everything - present))}"
        )


def test_a_code_is_never_reused_for_two_different_errors():
    """Two sentences under one code means one of them is shown in the wrong situation.

    The same code raised from several places is expected and fine - a dataset is not
    found in eight endpoints - as long as they all mean the same thing.
    """
    seen: dict[str, set[str]] = {}
    for path in (BACKEND / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name != "ApiError" or len(node.args) < 3:
                continue
            code, detail = node.args[1], node.args[2]
            if isinstance(code, ast.Constant) and isinstance(detail, ast.Constant):
                seen.setdefault(code.value, set()).add(detail.value)

    conflicting = {c: s for c, s in seen.items() if len(s) > 1}
    assert not conflicting, f"one code, several meanings: {conflicting}"


# ---- what the response actually looks like -------------------------------------------

def test_the_response_carries_both_the_code_and_the_sentence(admin):
    r = admin.get("/api/datasets/" + "0" * 32)
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "dataset_not_found"
    assert body["detail"] == "Dataset not found", "the sentence must not have moved"


def test_a_refusal_carries_its_code(viewer, dataset):
    r = viewer.delete(f"/api/datasets/{dataset}")
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"


def test_an_anonymous_request_carries_its_code(anon):
    body = anon.get("/api/datasets").json()
    assert body["code"] == "not_authenticated"


def test_a_conflict_carries_its_code(admin):
    r = admin.post(
        "/api/users",
        json={"username": "test_admin", "password": "abcdef1", "role": "viewer"},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "username_taken"


def test_the_lockout_response_keeps_its_retry_header(api):
    """The 429 is the one error with a header the interface reads. Rewriting the body
    must not have dropped it."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    codes = []
    for _ in range(7):
        r = client.post(
            "/api/auth/login",
            json={"username": "test_lockout_probe", "password": "wrong"},
        )
        codes.append(r.status_code)
        if r.status_code == 429:
            assert r.json()["code"] == "too_many_attempts"
            assert "retry-after" in {k.lower() for k in r.headers}
            break
    assert 429 in codes, codes

    from app.services import login_guard

    login_guard.clear_all()


def test_an_uncoded_error_still_returns_a_plain_detail(admin, dataset):
    """Errors carrying a column name or a parser's complaint were left as they were.
    They must still arrive, just without a code for the interface to translate."""
    r = admin.post(f"/api/datasets/{dataset}/data", json={"sort_by": "no_such_column"})
    assert r.status_code == 400
    body = r.json()
    assert "no_such_column" in body["detail"]
    assert "code" not in body
