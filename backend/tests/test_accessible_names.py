"""Every control has to say what it is, in the language the page is in.

A screen reader announces a control by its accessible name and nothing else. The row it
sits in, the column heading above it, the paragraph beside it - none of that reaches the
announcement. So a `<select>` with no name is read as "combo box", twelve times down the
languages page, and a checkbox in the permission grid was read as "datasets.delete",
which is the database's name for it and not anyone else's.

The opposite failure is as bad and less obvious: the settings pages named their help
buttons with the entire help paragraph, so moving focus along a row read three sentences
of explanation aloud before saying what the button was.

These are static checks over the JSX, which is where both mistakes are made.
"""

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"

# Anything the user can operate. `<button>` is excluded because its visible text names
# it; the ones that carry an icon and nothing else are covered by the literal check.
CONTROLS = ("input", "select", "textarea")

# Reachable from a route. pages/UsersPage.tsx is not - nothing links to it - and it is
# queued for deletion; checking it would be checking dead code.
UNREACHABLE = {"pages/UsersPage.tsx", "components/PasswordField.tsx"}

# A name is meant to be said in one breath. The longest real one here is the Arabic
# "جعل {{language}} اللغة الافتراضية"; the paragraph that caused the bug was 214
# characters.
MAX_NAME_LENGTH = 70


def sources() -> list[Path]:
    return [
        p
        for p in sorted(FRONTEND.rglob("*.tsx"))
        if p.relative_to(FRONTEND).as_posix() not in UNREACHABLE
    ]


def relative(path: Path) -> str:
    return path.relative_to(FRONTEND).as_posix()


def code(path: Path) -> str:
    """The file with its comments blanked out, newlines kept so lines still line up.

    ColumnSelect's docstring explains why it does not use a native `<select>`, and says
    so by writing one. Scanning the comment finds a control that does not exist.
    """
    src = path.read_text(encoding="utf-8")
    return re.sub(
        r"/\*.*?\*/|//[^\n]*",
        lambda m: re.sub(r"[^\n]", " ", m.group(0)),
        src,
        flags=re.S,
    )


def tags(src: str, names: tuple[str, ...]):
    """Yield (line, offset, tag text) for each opening tag of the given elements.

    The tag does not simply end at the next ">": an arrow function inside a handler -
    `onChange={(e) => set(e)}` - has one, and stopping there cuts the tag off before the
    attributes that follow it, which is exactly where a name usually sits. Only a ">"
    outside every brace closes the tag.
    """
    for match in re.finditer(r"<(" + "|".join(names) + r")\b", src):
        depth = 0
        i = match.end()
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            elif src[i] == ">" and depth == 0:
                break
            i += 1
        yield src[: match.start()].count("\n") + 1, match.start(), src[match.start() : i + 1]


def wrapped_in_label(src: str, position: int) -> bool:
    """True when an unclosed `<label` opens before this point - the wrapping form,
    which associates without needing an id."""
    before = src[:position]
    return before.count("<label") > before.count("</label>")


def named(tag: str) -> bool:
    return any(
        attribute in tag
        for attribute in ("aria-label", "aria-labelledby", "placeholder", "id=", "title=")
    )


def test_the_scan_sees_the_files_it_should():
    """Otherwise every assertion below passes by looking at nothing."""
    found = sources()
    assert len(found) > 40, found
    assert sum(len(list(tags(code(p), CONTROLS))) for p in found) > 50
    # The arrow-function trap, pinned: this tag's name sits past a ">" that does not
    # close it. Reading the tag as far as the first ">" reports it as nameless.
    sample = '<select value={v} onChange={(e) => go(e)} aria-label={t("k")}>'
    assert "aria-label" in next(iter(tags(sample, CONTROLS)))[2]


def test_every_control_carries_a_name():
    nameless = []
    for path in sources():
        src = code(path)
        for line, position, tag in tags(src, CONTROLS):
            if 'type="hidden"' in tag or 'type="file"' in tag:
                continue  # never announced; the file input is behind its own button
            if not named(tag) and not wrapped_in_label(src, position):
                nameless.append(f"{relative(path)}:{line}  {' '.join(tag.split())[:80]}")
    assert not nameless, "controls a screen reader announces only by role:\n" + "\n".join(nameless)


def test_no_name_is_written_in_english_in_the_source():
    """A literal here is a string no translator ever sees. "Close" sat in the admin
    drawer's header for as long as the drawer existed, on every page that used it."""
    literals = []
    for path in sources():
        src = code(path)
        for match in re.finditer(r'(aria-label|placeholder|title)="([^"]+)"', src):
            attribute, value = match.group(1), match.group(2)
            line = src[: match.start()].count("\n") + 1
            literals.append(f"{relative(path)}:{line}  {attribute}=\"{value}\"")
    assert not literals, "untranslated names in the source:\n" + "\n".join(literals)


def translated_names() -> list[tuple[str, str]]:
    """(source location, translation key) for every name taken from a translation."""
    out = []
    for path in sources():
        src = code(path)
        for match in re.finditer(r'aria-label=\{\s*t\(\s*"([\w.]+)"', src):
            out.append((f"{relative(path)}:{src[: match.start()].count(chr(10)) + 1}", match.group(1)))
    return out


def test_the_scan_finds_the_translated_names():
    found = translated_names()
    assert len(found) > 25, found
    assert any(key == "common.help" for _, key in found), "the help button's key is missing"


@pytest.mark.parametrize("language", ("ar", "en", "he"))
def test_a_name_is_a_name_and_not_a_paragraph(language):
    """BUG-019. `aria-label={text}` on the settings help button put the whole
    explanation where the word "help" belonged."""
    import io
    import json

    data = json.load(io.open(FRONTEND / "i18n" / f"{language}.json", encoding="utf-8"))

    def lookup(dotted: str):
        node = data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node if isinstance(node, str) else None

    too_long = []
    for where, key in translated_names():
        value = lookup(key)
        if value is None:
            continue  # key resolved at runtime, or a defaultValue carries it
        if len(value) > MAX_NAME_LENGTH:
            too_long.append(f"{where}  {key} = {value[:60]}... ({len(value)} chars)")
    assert not too_long, (
        f"{language}.json: names long enough to be read as prose:\n" + "\n".join(too_long)
    )


def test_every_label_is_attached_to_something():
    """`<label>Encoding</label><input/>` as siblings looks right and connects nothing.
    A label either wraps its control or points at it with htmlFor."""
    loose = []
    for path in sources():
        src = code(path)
        for match in re.finditer(r"<label\b([^>]*)>(.*?)</label>", src, re.S):
            attributes, body = match.group(1), match.group(2)
            if "htmlFor" in attributes:
                continue
            if re.search(r"<(input|select|textarea)\b", body):
                continue  # wraps its control
            line = src[: match.start()].count("\n") + 1
            loose.append(f"{relative(path)}:{line}  {' '.join(body.split())[:60]}")
    assert not loose, "labels attached to nothing:\n" + "\n".join(loose)
