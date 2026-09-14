"""A mark that says "this is UTF-8" must not become part of the first column's name.

Windows tools - Excel above all - write UTF-8 CSVs beginning with EF BB BF, a byte-order
mark. charset-normalizer reports such a file as plain "utf_8", and Python's utf_8 codec
has no reason to treat those three bytes as anything but a character, so the mark came
through as U+FEFF on the front of the first field. The preview's first column was named
"﻿plate": invisible on screen, not equal to "plate", and not the name the table
would end up with once DuckDB - which does strip it - had loaded the file.

So the reader was shown one name for the column and the system used another. These check
both halves of the fix: naming the codec that eats the mark, and taking it off by hand in
the one case a codec cannot cover, which is the reader overriding the encoding by hand.
"""

import codecs
from pathlib import Path

import pytest

from app.services import ingestion
from conftest import wait_for_job
from helpers import rows_as_dicts

HEADER = "plate,make\n"
BODY = "1234,Toyota\n5678,Kia\n"
ARABIC = "اللوحة,الماركة\n1234,تويوتا\n"


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# ---- detection ------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mark, text_encoding, expected",
    [
        (codecs.BOM_UTF8, "utf-8", "utf_8_sig"),
        (codecs.BOM_UTF16_LE, "utf-16-le", "utf_16"),
        (codecs.BOM_UTF16_BE, "utf-16-be", "utf_16"),
        (codecs.BOM_UTF32_LE, "utf-32-le", "utf_32"),
        (codecs.BOM_UTF32_BE, "utf-32-be", "utf_32"),
    ],
)
def test_a_byte_order_mark_names_the_codec_that_eats_it(tmp_path, mark, text_encoding, expected):
    """Every codec named here consumes the mark on the way in. That is the point of
    naming it rather than guessing: the fix and the label are the same act."""
    path = write(tmp_path, "marked.csv", mark + (HEADER + BODY).encode(text_encoding))
    assert ingestion.detect_encoding(path) == expected


def test_a_utf32_file_is_not_read_as_utf16(tmp_path):
    """The trap in the lookup table, pinned.

    FF FE 00 00 is the UTF-32-LE mark and it *begins with* FF FE, the UTF-16-LE one. A
    table that tests the two-byte marks first matches every UTF-32-LE file as UTF-16 and
    decodes the whole thing into mojibake - and it would do so quietly, since the result
    is a successful decode of the wrong characters.
    """
    assert codecs.BOM_UTF32_LE.startswith(codecs.BOM_UTF16_LE), "the trap this guards"
    path = write(tmp_path, "wide.csv", codecs.BOM_UTF32_LE + (HEADER + BODY).encode("utf-32-le"))

    encoding = ingestion.detect_encoding(path)
    assert encoding == "utf_32"
    columns, _ = ingestion.read_preview(path, encoding, ",", True, 5)
    assert columns == ["plate", "make"]


def test_a_file_without_a_mark_is_still_detected_the_old_way(tmp_path):
    """The shortcut must not have become the only path: a file with no mark still goes
    to charset-normalizer, which is what reads the Hebrew codepages this app is full of.

    The sample is repeated because detection is statistical - twenty bytes of Hebrew are
    as consistent with Thai as with Hebrew, and guessing from them says nothing about
    whether the right code ran. test_ingestion.py checks the guess itself against the
    real fixture; what matters here is only that the guess is still being made.
    """
    hebrew = ("מספר,יצרן,דגם\n1234,קיה,ספורטאז׳\n5678,טויוטה,קורולה\n" * 40).encode("cp1255")
    path = write(tmp_path, "hebrew.csv", hebrew)
    guessed = ingestion.detect_encoding(path)
    assert guessed not in {"utf_8_sig", "utf_16", "utf_32"}, "no mark, so no mark-derived answer"
    normalised = guessed.lower().replace("-", "").replace("_", "")
    assert normalised in {"cp1255", "windows1255", "hebrew", "iso88598", "iso88598i"}, guessed


# ---- preview and normalisation ----------------------------------------------------------

def test_the_first_column_is_named_without_the_mark(tmp_path):
    path = write(tmp_path, "bom.csv", codecs.BOM_UTF8 + (HEADER + BODY).encode("utf-8"))
    encoding = ingestion.detect_encoding(path)
    columns, rows = ingestion.read_preview(path, encoding, ",", True, 5)
    assert columns == ["plate", "make"]
    assert rows == [["1234", "Toyota"], ["5678", "Kia"]]


def test_an_arabic_header_survives_the_mark_intact(tmp_path):
    """Stripping one character off the front of a field is the kind of fix that takes
    the wrong character when the next one is not ASCII."""
    path = write(tmp_path, "arabic.csv", codecs.BOM_UTF8 + ARABIC.encode("utf-8"))
    encoding = ingestion.detect_encoding(path)
    columns, rows = ingestion.read_preview(path, encoding, ",", True, 5)
    assert columns == ["اللوحة", "الماركة"]
    assert rows == [["1234", "تويوتا"]]


def test_the_mark_is_removed_even_when_the_reader_names_the_wrong_encoding(tmp_path):
    """The wizard lets the reader override detection, and plain "utf-8" for a file that
    carries a BOM is a reasonable thing to choose. The codec then keeps the mark, so
    this is the case the second half of the fix exists for."""
    path = write(tmp_path, "bom.csv", codecs.BOM_UTF8 + (HEADER + BODY).encode("utf-8"))
    columns, _ = ingestion.read_preview(path, "utf-8", ",", True, 5)
    assert columns == ["plate", "make"]


def test_a_headerless_file_keeps_the_mark_out_of_its_first_value(tmp_path):
    """With no header the first field is data, and a plate number with an invisible
    character in front of it does not match the same plate number typed into search."""
    path = write(tmp_path, "bom.csv", codecs.BOM_UTF8 + BODY.encode("utf-8"))
    encoding = ingestion.detect_encoding(path)
    _, rows = ingestion.read_preview(path, encoding, ",", False, 5)
    assert rows[0] == ["1234", "Toyota"]


def test_the_normalised_file_does_not_start_with_a_mark(tmp_path):
    """The file handed to DuckDB. DuckDB strips a leading mark itself, which is why this
    defect looked cosmetic - but the normalised file is the app's own artefact and has no
    business carrying one."""
    src = write(tmp_path, "bom.csv", codecs.BOM_UTF8 + (HEADER + BODY).encode("utf-8"))
    dst = tmp_path / "normalised.csv"
    ingestion.normalize_to_utf8(src, dst, ingestion.detect_encoding(src), ",")
    assert not dst.read_bytes().startswith(codecs.BOM_UTF8)
    assert dst.read_text(encoding="utf-8").startswith("plate,make")


# ---- the whole way through --------------------------------------------------------------

def test_an_excel_csv_imports_under_the_name_the_preview_showed(admin, tmp_path):
    """The bug stated as what it cost: the name on screen and the name in the table were
    different, so anything built on the preview's spelling addressed a column that did
    not exist."""
    path = write(tmp_path, "QA_TEST_bom.csv", codecs.BOM_UTF8 + (HEADER + BODY).encode("utf-8"))

    with open(path, "rb") as f:
        r = admin.post("/api/datasets/upload", files={"file": ("QA_TEST_bom.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    dataset = body["dataset_id"]

    assert body["detected_encoding"] == "utf_8_sig"
    assert body["columns"] == ["plate", "make"], body["columns"]
    assert not body["columns"][0].startswith("﻿")

    r = admin.post(
        f"/api/datasets/{dataset}/import",
        json={"encoding": body["detected_encoding"], "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, r.json()["id"])["status"] == "done"

    stored = admin.get(f"/api/datasets/{dataset}").json()["columns"]
    assert stored == body["columns"], "the preview promised one name and the table has another"

    # and the name actually works as a name
    rows = rows_as_dicts(
        admin, dataset, source="raw",
        filters=[{"column": "plate", "op": "eq", "value": "1234"}],
    )
    assert [row["make"] for row in rows] == ["Toyota"]

    admin.delete(f"/api/datasets/{dataset}")
