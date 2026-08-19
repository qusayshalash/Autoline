"""Import quality report - what the file actually contained, and what survived.

An import can succeed and still lose data: the transcoder replaces bytes that are not
valid in the declared encoding, and DuckDB's reader is deliberately lenient about
malformed rows. Neither says anything at the time. This module goes and looks, so the
answer is on screen instead of waiting to be discovered.

Three passes, each cheap enough to justify:

  1. a byte scan of the original upload, for bytes the encoding cannot represent;
  2. one CSV pass, for the true record count and the shape of every row;
  3. one aggregate query per table, for the per-column profile.

Everything is measured against the *original file*, never against the database's own
idea of itself - a report derived only from the table could not detect a row the loader
never inserted.
"""

import codecs
import csv
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from app.config import settings
from app.db import catalog
from app.db.connection import datasets, read_locked
from app.services import sql_utils

csv.field_size_limit(10_000_000)

# Damaged values reported individually; beyond this only the count is kept, so a
# thoroughly broken file cannot produce a megabyte of JSON.
MAX_REPORTED_SAMPLES = 25

# A column at or below this fill rate is called out as mostly empty.
MOSTLY_EMPTY_AT = 5.0

# Share of a column's values that must be zero-padded before it is called an identifier
# column. Without a floor, a handful of incidental "0..." values in a free-text column
# raises the same flag as a genuine padded key, and the useful signal drowns.
ZERO_PADDED_SHARE = 10.0

Progress = Callable[[str], None]


@dataclass
class _Damage:
    row: int
    column: str
    value: str
    byte_offset: int
    byte: str


@dataclass
class _Scan:
    """Result of reading the original upload."""

    records: int = 0
    data_rows: int = 0
    field_counts: dict[int, int] = field(default_factory=dict)
    undecodable_bytes: int = 0
    damaged_values: int = 0
    samples: list[_Damage] = field(default_factory=list)
    header: list[str] = field(default_factory=list)


def _undecodable_byte_values(encoding: str) -> set[int]:
    """Byte values the encoding has no character for.

    Only meaningful for single-byte encodings, which is what this matters for: the
    Israeli registry exports are Windows-1255, and cp1255 leaves a dozen positions
    undefined. For a multi-byte encoding the set comes back empty and the byte scan is
    skipped in favour of the CSV pass, which still catches the damage.
    """
    try:
        decoder = codecs.getdecoder(encoding)
    except LookupError:
        return set()
    bad = set()
    for b in range(256):
        try:
            decoder(bytes([b]))
        except UnicodeDecodeError:
            bad.add(b)
        except Exception:  # noqa: BLE001 - a multi-byte codec; not a single-byte hole
            return set()
    return bad


def _scan_original(path: Path, encoding: str, delimiter: str, on_progress: Progress) -> _Scan:
    """Byte scan for undecodable bytes, then one CSV pass for structure."""
    scan = _Scan()

    bad_values = _undecodable_byte_values(encoding)
    bad_rows: dict[int, int] = {}  # 0-based record index -> byte offset of first damage
    if bad_values:
        on_progress("scanning:bytes")
        offset = 0
        newlines = 0
        with open(path, "rb") as f:
            while True:
                chunk = f.read(8 << 20)
                if not chunk:
                    break
                for i, b in enumerate(chunk):
                    if b == 0x0A:
                        newlines += 1
                    elif b in bad_values:
                        scan.undecodable_bytes += 1
                        bad_rows.setdefault(newlines, offset + i)
                offset += len(chunk)

    # The CSV pass is what turns byte offsets into "row 1,045,938, column degem_manoa",
    # and is the only reliable way to count records when a field may embed a newline.
    on_progress("scanning:records")
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for index, row in enumerate(reader):
            scan.records += 1
            scan.field_counts[len(row)] = scan.field_counts.get(len(row), 0) + 1
            if index == 0:
                scan.header = row
                continue
            if "�" in "".join(row):
                for col_index, value in enumerate(row):
                    if "�" not in value:
                        continue
                    scan.damaged_values += 1
                    if len(scan.samples) < MAX_REPORTED_SAMPLES:
                        name = (
                            scan.header[col_index]
                            if col_index < len(scan.header)
                            else f"column_{col_index + 1}"
                        )
                        offset = bad_rows.get(index, -1)
                        scan.samples.append(
                            _Damage(
                                row=index,
                                column=name,
                                value=value,
                                byte_offset=offset,
                                byte=_byte_at(path, offset),
                            )
                        )
            if scan.records % 500_000 == 0:
                on_progress(f"scanning:{scan.records}")

    scan.data_rows = max(0, scan.records - 1)
    return scan


def _byte_at(path: Path, offset: int) -> str:
    if offset < 0:
        return ""
    with open(path, "rb") as f:
        f.seek(offset)
        b = f.read(1)
    return f"0x{b[0]:02X}" if b else ""


def _fill_pct(filled: int, total: int) -> float:
    if not total:
        return 0.0
    if filled == total:
        return 100.0
    # a partially filled column stops just short of 100, however small the gap
    return min(99.99, round(filled * 100.0 / total, 2))


def _profile_columns(dataset_id: str, table: str) -> tuple[list[dict], int, int]:
    """Fill rate, cardinality and value length per column, plus duplicate rows."""
    cur = datasets.cursor(dataset_id)
    columns = sql_utils.table_columns(dataset_id, table)
    table_sql = sql_utils.quote_ident(table)
    if not columns:
        return [], 0, 0

    total = cur.execute(f"SELECT COUNT(*) FROM {table_sql}").fetchone()[0]

    selects = []
    for c in columns:
        col = sql_utils.quote_ident(c)
        selects.append(f"COUNT({col})")
        selects.append(f"COUNT(*) FILTER (WHERE {col} = '')")
        selects.append(f"COUNT(DISTINCT {col})")
        selects.append(f"MIN(LENGTH({col}))")
        selects.append(f"MAX(LENGTH({col}))")
        selects.append(f"COUNT(*) FILTER (WHERE {col} LIKE '0%' AND LENGTH({col}) > 1)")
    row = cur.execute(f"SELECT {', '.join(selects)} FROM {table_sql}").fetchone()

    profiles = []
    for i, name in enumerate(columns):
        non_null, empty, distinct, min_len, max_len, zero_led = row[i * 6 : i * 6 + 6]
        filled = non_null - empty
        profiles.append(
            {
                "name": name,
                "filled": filled,
                "missing": total - filled,
                # never round up to a flat 100% while values are actually missing - a
                # column showing "100% filled, 82 missing" reads as a bug in the report
                "fill_pct": _fill_pct(filled, total),
                "distinct": distinct,
                "min_length": min_len,
                "max_length": max_len,
                "zero_padded": zero_led,
            }
        )

    cols_sql = ", ".join(sql_utils.quote_ident(c) for c in columns)
    unique_rows = cur.execute(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT {cols_sql} FROM {table_sql})"
    ).fetchone()[0]
    return profiles, total, total - unique_rows


def _warnings(scan: Optional[_Scan], loaded: int, profiles: list[dict], duplicates: int) -> list[dict]:
    """Findings, as codes the frontend translates rather than baked-in English."""
    out: list[dict] = []

    if scan:
        expected = max(scan.field_counts, key=lambda k: scan.field_counts[k]) if scan.field_counts else 0
        ragged = sum(n for width, n in scan.field_counts.items() if width != expected)
        if ragged:
            out.append({"level": "problem", "code": "ragged_rows", "count": ragged, "expected": expected})
        if scan.data_rows != loaded:
            out.append(
                {
                    "level": "problem",
                    "code": "rows_dropped",
                    "count": scan.data_rows - loaded,
                    "in_file": scan.data_rows,
                    "loaded": loaded,
                }
            )
        if scan.damaged_values:
            out.append(
                {
                    "level": "warning",
                    "code": "encoding_replacements",
                    "count": scan.damaged_values,
                    "bytes": scan.undecodable_bytes,
                }
            )

    if duplicates:
        out.append({"level": "warning", "code": "duplicate_rows", "count": duplicates})

    for p in profiles:
        if p["filled"] == 0:
            out.append({"level": "warning", "code": "empty_column", "column": p["name"]})
        elif p["fill_pct"] <= MOSTLY_EMPTY_AT:
            out.append(
                {"level": "info", "code": "mostly_empty_column", "column": p["name"], "pct": p["fill_pct"]}
            )
        if p["filled"] and p["distinct"] == 1:
            out.append({"level": "info", "code": "constant_column", "column": p["name"]})
        if p["filled"] and p["zero_padded"] * 100.0 / p["filled"] >= ZERO_PADDED_SHARE:
            out.append(
                {"level": "info", "code": "zero_padded_column", "column": p["name"], "count": p["zero_padded"]}
            )
    return out


@read_locked
def analyze(dataset_id: str, on_progress: Optional[Progress] = None) -> dict:
    """Builds the report and returns it. Also stored on the dataset by the caller."""
    progress: Progress = on_progress or (lambda _s: None)
    started = time.perf_counter()

    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ValueError("Dataset not found")

    encoding = row.get("encoding") or "utf-8"
    delimiter = row.get("delimiter") or ","

    upload_dir = settings.uploads_dir / dataset_id
    original = next(iter(upload_dir.glob("raw.*")), None)

    scan: Optional[_Scan] = None
    if original and original.is_file():
        scan = _scan_original(original, encoding, delimiter, progress)

    progress("profiling")
    profiles, loaded, duplicates = _profile_columns(dataset_id, "raw_data")

    findings = _warnings(scan, loaded, profiles, duplicates)
    levels = {w["level"] for w in findings}
    verdict = "problem" if "problem" in levels else ("warning" if "warning" in levels else "clean")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "verdict": verdict,
        "source_file": {
            "name": row.get("original_filename"),
            "bytes": original.stat().st_size if original and original.is_file() else None,
            "available": bool(original and original.is_file()),
            "encoding": encoding,
            "delimiter": delimiter,
        },
        "rows": {
            "in_file": scan.data_rows if scan else None,
            "loaded": loaded,
            "duplicates": duplicates,
        },
        "structure": {
            "columns": len(profiles),
            "field_count_spread": {str(k): v for k, v in sorted(scan.field_counts.items())}
            if scan
            else {},
        },
        "encoding_issues": {
            "undecodable_bytes": scan.undecodable_bytes if scan else 0,
            "damaged_values": scan.damaged_values if scan else 0,
            "samples": [vars(d) for d in scan.samples] if scan else [],
        },
        "columns": profiles,
        "findings": findings,
    }


def run_quality_job(dataset_id: str, job_id: str) -> None:
    """Background wrapper, so a multi-million-row file does not hold a request open."""
    try:
        catalog.update_job(job_id, status="running", progress="starting")
        report = analyze(dataset_id, lambda p: catalog.update_job(job_id, progress=p))
        catalog.update_dataset(dataset_id, quality_json=report)
        catalog.update_job(job_id, status="done", progress="ready", result_json={"verdict": report["verdict"]})
    except Exception as exc:  # noqa: BLE001 - surface the failure on the job record
        catalog.update_job(job_id, status="error", error_message=str(exc))
