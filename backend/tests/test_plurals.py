"""A sentence that carries a number has to agree with it.

Arabic does not have one plural. It has six categories, and the noun changes in each:
one دقيقة, two دقيقتان, three-to-ten دقائق, eleven-and-up دقيقة again. A single string
with {{count}} in it is therefore wrong for most values - "قبل 6 دقيقة" is the shape it
took, and it appeared on every row of the activity log.

i18next picks the form from Intl.PluralRules using a `_zero`/`_one`/`_two`/`_few`/
`_many`/`_other` suffix. A form that is missing does not fail; it silently falls back to
`_other`, which is the wrong grammar delivered quietly. That is what these check.
"""

import io
import json
from pathlib import Path

import pytest

LOCALES = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "i18n"

# What CLDR requires of each language this app ships. Arabic needs all six; Hebrew
# distinguishes one and two; English only singular and plural.
REQUIRED_FORMS = {
    "ar": {"zero", "one", "two", "few", "many", "other"},
    "he": {"one", "two", "other"},
    "en": {"one", "other"},
}
ALL_SUFFIXES = ("_zero", "_one", "_two", "_few", "_many", "_other")


def flatten(node, prefix="") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def strings(language: str) -> dict[str, str]:
    return flatten(json.load(io.open(LOCALES / f"{language}.json", encoding="utf-8")))


def split_form(key: str):
    for suffix in ALL_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)], suffix[1:]
    return key, None


def forms_by_base(language: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for key in strings(language):
        base, form = split_form(key)
        if form:
            out.setdefault(base, set()).add(form)
    return out


def test_something_is_actually_pluralised():
    """Otherwise every assertion below passes by having nothing to check."""
    assert len(forms_by_base("ar")) >= 10, forms_by_base("ar")


@pytest.mark.parametrize("language", ("ar", "en", "he"))
def test_each_pluralised_key_has_every_form_its_language_needs(language):
    required = REQUIRED_FORMS[language]
    incomplete = {
        base: sorted(required - forms)
        for base, forms in forms_by_base(language).items()
        if required - forms
    }
    assert not incomplete, (
        f"{language}.json is missing plural forms: {incomplete} - i18next falls back to "
        "_other, which reads as the wrong grammar rather than as an error"
    )


def test_the_languages_pluralise_the_same_keys():
    """A string pluralised in Arabic and left flat in Hebrew is half a fix."""
    bases = {lang: set(forms_by_base(lang)) for lang in REQUIRED_FORMS}
    everything = set().union(*bases.values())
    for language, present in bases.items():
        assert not (everything - present), (
            f"{language}.json does not pluralise: {', '.join(sorted(everything - present))}"
        )


@pytest.mark.parametrize("language", ("ar", "en", "he"))
def test_no_flat_key_is_left_beside_its_plural_forms(language):
    """i18next stops consulting the bare key once forms exist, so one left behind is
    dead weight that reads like the live value."""
    all_keys = set(strings(language))
    stale = sorted(base for base in forms_by_base(language) if base in all_keys)
    assert not stale, f"{language}.json still holds unused flat keys: {', '.join(stale)}"


@pytest.mark.parametrize("language", ("ar", "en", "he"))
def test_no_plural_form_is_blank(language):
    blank = sorted(k for k, v in strings(language).items() if split_form(k)[1] and not str(v).strip())
    assert not blank, f"{language}.json has empty plural forms: {', '.join(blank)}"


def test_arabic_spells_small_counts_out_rather_than_printing_them():
    """The point of the one/two forms: Arabic says "مستخدم واحد" and "مستخدمان", not
    "1 مستخدم" and "2 مستخدم". A {{count}} left in those forms means the form was added
    without being translated."""
    values = strings("ar")
    for base in forms_by_base("ar"):
        for form in ("one", "two"):
            text = values.get(f"{base}_{form}", "")
            assert "{{count}}" not in text, (
                f"ar.json '{base}_{form}' still prints the number: {text!r}"
            )


def test_the_forms_that_show_a_figure_keep_their_placeholder():
    """few/many/other print the number, so losing {{count}} there turns "11 files" into
    "files"."""
    for language in REQUIRED_FORMS:
        values = strings(language)
        for base in forms_by_base(language):
            english_other = strings("en").get(f"{base}_other", "")
            if "{{count}}" not in english_other:
                continue  # a sentence that never shows the figure in any language
            for form in ("few", "many", "other"):
                key = f"{base}_{form}"
                if key in values:
                    assert "{{count}}" in values[key], f"{language}.json '{key}' lost its number"
