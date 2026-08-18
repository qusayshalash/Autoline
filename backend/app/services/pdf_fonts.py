"""Finds a font that can actually draw this data, and registers it with reportlab.

reportlab's built-in fonts are Latin-1 only. Drawing Arabic or Hebrew with them produces
a page of .notdef boxes - the export succeeds, the file opens, and every label is a black
square. Since these datasets are Hebrew and the interface is Arabic, that is the normal
case here rather than an edge one, so a real font has to be found before anything is
drawn.

Nothing is bundled: the search walks the platform's own font directories and takes the
first face that covers the scripts in question. Coverage is verified against the font's
character map rather than assumed from its name, because "Arial" on one machine is not
the same file as "Arial" on another.
"""

import logging
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

FALLBACK = "Helvetica"
_REGISTERED_NAME = "DataFont"

# Ordered by preference. Arial and Tahoma ship with Windows and cover both scripts;
# DejaVu and Liberation are the usual Linux faces; the macOS entries come last.
_CANDIDATES = (
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
)

# One character per script that has to be drawable. The Arabic sample is a *presentation
# form* (U+FEE3) because arabic_reshaper converts text to those before it is drawn - a
# font can carry plain Arabic and still lack the contextual shapes.
_PROBES = {
    "arabic": 0xFEE3,
    "hebrew": 0x05D0,
    "latin": 0x0041,
}

_resolved: str | None = None


def _covers(path: Path) -> set[str]:
    try:
        face = TTFont("probe", str(path)).face
    except Exception:  # noqa: BLE001 - an unreadable or exotic font is simply skipped
        return set()
    cmap = face.charToGlyph
    return {name for name, code in _PROBES.items() if code in cmap}


def data_font() -> str:
    """The font name to draw table content with. Resolved once per process.

    Returns reportlab's built-in Helvetica when nothing better is installed, which keeps
    Latin exports working; the log line says what was lost so a box-filled PDF is never
    a silent mystery.
    """
    global _resolved
    if _resolved is not None:
        return _resolved

    best: tuple[int, Path] | None = None
    for candidate in _CANDIDATES:
        path = Path(candidate)
        if not path.is_file():
            continue
        covered = _covers(path)
        if "latin" not in covered:
            continue
        score = len(covered)
        if best is None or score > best[0]:
            best = (score, path)
        if score == len(_PROBES):
            break

    if best is None:
        logger.warning(
            "No font covering Arabic/Hebrew was found; PDF exports will fall back to %s "
            "and non-Latin text will render as boxes.",
            FALLBACK,
        )
        _resolved = FALLBACK
        return _resolved

    score, path = best
    try:
        pdfmetrics.registerFont(TTFont(_REGISTERED_NAME, str(path)))
    except Exception:  # noqa: BLE001
        logger.warning("Could not register font %s; falling back to %s", path, FALLBACK)
        _resolved = FALLBACK
        return _resolved

    if score < len(_PROBES):
        logger.warning(
            "Font %s does not cover every script (%d/%d probes); some characters may "
            "render as boxes.",
            path,
            score,
            len(_PROBES),
        )
    logger.info("PDF exports will use %s", path)
    _resolved = _REGISTERED_NAME
    return _resolved
