"""Upload -> detect -> preview -> normalize -> load pipeline.

Every stage that touches the file body works on bounded chunks/lines, never the whole
file at once, so a multi-hundred-MB / multi-million-row CSV never has to fit in memory.
"""

import csv
import shutil
from pathlib import Path
from typing import Callable, Optional

from charset_normalizer import from_bytes
from fastapi import UploadFile

from app.config import settings
from app.db import catalog
from app.db.connection import datasets

ALLOWED_DELIMITERS = [",", ";", "|", "\t"]


class InsufficientDiskSpace(Exception):
    """Raised mid-upload rather than pre-checked against Content-Length: that header is
    absent for a chunked request and untrustworthy even when present, so the only figure
    worth acting on is how much room is actually left, checked as the file grows.
    """


def dataset_upload_dir(dataset_id: str) -> Path:
    d = settings.uploads_dir / dataset_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def raw_path(dataset_id: str, ext: str) -> Path:
    return dataset_upload_dir(dataset_id) / f"raw{ext}"


def normalized_path(dataset_id: str) -> Path:
    return dataset_upload_dir(dataset_id) / "normalized.csv"


async def save_upload_stream(dataset_id: str, file: UploadFile, ext: str) -> Path:
    """Writes the upload to disk a chunk at a time, refusing to fill the disk doing it.

    Checked after every chunk rather than once at the start: the file's total size is
    not known in advance - some clients never send Content-Length, and none of them can
    be trusted to send an honest one - and this same disk is also where every other
    dataset's tables live, so what is free can shrink for reasons that have nothing to
    do with this particular upload.

    A rejected upload leaves nothing behind: the partial file is removed before the
    error is raised, rather than left for the next cleanup pass to find.
    """
    dest = raw_path(dataset_id, ext)
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(settings.upload_chunk_bytes)
                if not chunk:
                    break
                out.write(chunk)
                if shutil.disk_usage(dest.parent).free < settings.min_free_disk_bytes:
                    raise InsufficientDiskSpace(
                        f"Not enough free disk space to continue this upload "
                        f"(need at least {settings.min_free_disk_bytes:,} bytes free)."
                    )
    except InsufficientDiskSpace:
        dest.unlink(missing_ok=True)
        raise
    return dest


def detect_encoding(path: Path) -> str:
    with open(path, "rb") as f:
        sample = f.read(settings.detection_sample_bytes)
    if not sample:
        return "utf-8"
    match = from_bytes(sample).best()
    if match is None:
        return "utf-8"
    return match.encoding


def detect_delimiter(path: Path, encoding: str) -> str:
    with open(path, "rb") as f:
        sample = f.read(settings.detection_sample_bytes)
    text = sample.decode(encoding, errors="replace")
    lines = text.splitlines()[:20]
    sample_text = "\n".join(lines)
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters="".join(ALLOWED_DELIMITERS))
        if dialect.delimiter in ALLOWED_DELIMITERS:
            return dialect.delimiter
    except csv.Error:
        pass
    # fallback: whichever candidate has the most consistent per-line count
    best_delim, best_score = ",", -1
    for delim in ALLOWED_DELIMITERS:
        counts = [line.count(delim) for line in lines if line]
        if not counts or max(counts) == 0:
            continue
        consistency = counts.count(counts[0])
        score = consistency * counts[0]
        if score > best_score:
            best_delim, best_score = delim, score
    return best_delim


def read_preview(
    path: Path, encoding: str, delimiter: str, has_header: bool, limit: int
) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        first = next(reader, [])
        if has_header:
            columns = first
            rows: list[list[str]] = []
        else:
            columns = [f"column_{i + 1}" for i in range(len(first))]
            rows = [first]
        for row in reader:
            if len(rows) >= limit:
                break
            rows.append(row)
    return columns, rows


def normalize_to_utf8(
    src_path: Path,
    dst_path: Path,
    encoding: str,
    delimiter: str,
    on_progress: Optional[Callable[[int], None]] = None,
) -> None:
    """Transcode to UTF-8 *and* re-serialize through csv.reader/writer so the output is
    a single canonical dialect (proper `""` quote-escaping, one row per record even if a
    field embeds a raw newline). Real-world exports are often inconsistent here - doing
    this once up front means DuckDB's own reader never has to guess a dialect later.
    """
    lines_done = 0
    report_every = 200_000
    with open(src_path, encoding=encoding, errors="replace", newline="") as fin, open(
        dst_path, "w", encoding="utf-8", newline=""
    ) as fout:
        reader = csv.reader(fin, delimiter=delimiter)
        writer = csv.writer(fout, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        for row in reader:
            writer.writerow(row)
            lines_done += 1
            if on_progress and lines_done % report_every == 0:
                on_progress(lines_done)
    if on_progress:
        on_progress(lines_done)


def _validate_delimiter(delimiter: str) -> str:
    if delimiter not in ALLOWED_DELIMITERS:
        raise ValueError(f"Unsupported delimiter: {delimiter!r}")
    return delimiter


def import_csv_to_duckdb(
    dataset_id: str, csv_path: Path, delimiter: str, has_header: bool
) -> tuple[list[str], int]:
    delimiter = _validate_delimiter(delimiter)
    lock = datasets.write_lock(dataset_id)
    with lock:
        cur = datasets.cursor(dataset_id)
        cur.execute("DROP TABLE IF EXISTS raw_data")
        cur.execute("DROP TABLE IF EXISTS cleaned_data")
        escaped_path = str(csv_path).replace("'", "''")
        cur.execute(
            f"""
            CREATE TABLE raw_data AS
            SELECT * FROM read_csv(
                '{escaped_path}',
                delim=$delim,
                header=$header,
                quote='"',
                escape='"',
                strict_mode=false,
                null_padding=true,
                ignore_errors=true,
                sample_size=-1,
                all_varchar=true,
                parallel=false
            )
            """,
            {"delim": delimiter, "header": has_header},
        )
        columns = [r[0] for r in cur.execute("DESCRIBE raw_data").fetchall()]
        row_count = cur.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0]
    return columns, row_count


def run_import_job(dataset_id: str, job_id: str, encoding: str, delimiter: str, has_header: bool) -> None:
    try:
        catalog.update_job(job_id, status="running", progress="normalizing")
        catalog.update_dataset(dataset_id, status="normalizing")

        src = find_raw_path(dataset_id)
        dst = normalized_path(dataset_id)

        def progress(lines: int) -> None:
            catalog.update_job(job_id, progress=f"normalizing:{lines}")

        normalize_to_utf8(src, dst, encoding, delimiter, on_progress=progress)

        catalog.update_job(job_id, progress="importing")
        catalog.update_dataset(dataset_id, status="importing")

        columns, row_count = import_csv_to_duckdb(dataset_id, dst, delimiter, has_header)

        raw_bytes = src.stat().st_size
        catalog.update_dataset(
            dataset_id,
            status="ready",
            error_message=None,
            encoding=encoding,
            delimiter=delimiter,
            has_header=has_header,
            columns_json=columns,
            row_count_raw=row_count,
            raw_file_bytes=raw_bytes,
        )

        # The dataset is usable from here on; the quality report is extra information
        # about the import that just happened, so a failure to produce it must not turn
        # a successful import into a failed one.
        catalog.update_job(job_id, progress="analyzing")
        verdict = None
        try:
            from app.services import quality  # imported late: quality reads the tables

            report = quality.analyze(
                dataset_id, lambda p: catalog.update_job(job_id, progress=f"analyzing:{p}")
            )
            catalog.update_dataset(dataset_id, quality_json=report)
            verdict = report["verdict"]
        except Exception as exc:  # noqa: BLE001
            catalog.update_dataset(dataset_id, quality_json=None)
            print(f"[import] quality analysis failed for {dataset_id}: {exc}")

        catalog.update_job(
            job_id,
            status="done",
            progress="ready",
            result_json={"row_count": row_count, "quality_verdict": verdict},
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure to the job/dataset record
        catalog.update_dataset(dataset_id, status="error", error_message=str(exc))
        catalog.update_job(job_id, status="error", error_message=str(exc))


def find_raw_path(dataset_id: str) -> Path:
    d = dataset_upload_dir(dataset_id)
    matches = list(d.glob("raw.*"))
    if not matches:
        raise FileNotFoundError(f"No raw upload found for dataset {dataset_id}")
    return matches[0]
