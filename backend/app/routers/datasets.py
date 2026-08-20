import csv
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi import File as FastAPIFile

from app.auth import get_current_user, require_permission
from app.services import clocks
from app.config import settings
from app.db import admin as admin_db
from app.db import catalog
from app.db.connection import datasets as dataset_connections
from app.jobs import submit
from app.models.schemas import (
    DatasetOut,
    ImportConfig,
    JobOut,
    QualityReport,
    UploadResponse,
)
from app.services import ingestion, quality

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# Errors read_preview/normalize can raise for user-supplied encoding/delimiter values
# that don't correspond to anything real - surfaced as a clean 400 instead of a 500.
_BAD_IMPORT_CONFIG_ERRORS = (LookupError, TypeError, ValueError, csv.Error, UnicodeError, FileNotFoundError)


def _quality_verdict(row: dict) -> str | None:
    raw = row.get("quality_json")
    if not raw:
        return None
    try:
        return json.loads(raw).get("verdict")
    except (TypeError, ValueError):
        return None


def _dataset_out(row: dict) -> DatasetOut:
    columns = json.loads(row["columns_json"]) if row.get("columns_json") else []
    return DatasetOut(
        quality_verdict=_quality_verdict(row),
        id=row["id"],
        original_filename=row["original_filename"],
        status=row["status"],
        error_message=row.get("error_message"),
        encoding=row.get("encoding"),
        delimiter=row.get("delimiter"),
        has_header=row.get("has_header"),
        columns=columns,
        row_count_raw=row.get("row_count_raw"),
        row_count_cleaned=row.get("row_count_cleaned"),
        raw_file_bytes=row.get("raw_file_bytes"),
        cleaned_file_bytes=row.get("cleaned_file_bytes"),
        created_at=clocks.iso(row.get("created_at")),
        updated_at=clocks.iso(row.get("updated_at")),
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(
    file: UploadFile = FastAPIFile(...), user: dict = Depends(require_permission("datasets.upload"))
) -> UploadResponse:
    dataset_id = catalog.new_id()
    catalog.create_dataset(dataset_id, file.filename or "upload.csv")

    ext = "".join(ch for ch in (("." + file.filename.split(".")[-1]) if file.filename and "." in file.filename else ".csv") if ch.isalnum() or ch == ".") or ".csv"
    try:
        saved_path = await ingestion.save_upload_stream(dataset_id, file, ext)
    except ingestion.InsufficientDiskSpace as exc:
        catalog.update_dataset(dataset_id, status="error", error_message=str(exc))
        raise HTTPException(413, str(exc)) from exc

    encoding = ingestion.detect_encoding(saved_path)
    delimiter = ingestion.detect_delimiter(saved_path, encoding)
    try:
        columns, preview_rows = ingestion.read_preview(
            saved_path, encoding, delimiter, has_header=True, limit=settings.preview_row_limit
        )
    except _BAD_IMPORT_CONFIG_ERRORS as exc:
        catalog.update_dataset(dataset_id, status="error", error_message=str(exc))
        raise HTTPException(400, f"Could not read the uploaded file: {exc}") from exc

    raw_bytes = saved_path.stat().st_size
    catalog.update_dataset(
        dataset_id,
        status="preview",
        encoding=encoding,
        delimiter=delimiter,
        has_header=True,
        columns_json=columns,
        raw_file_bytes=raw_bytes,
    )

    return UploadResponse(
        dataset_id=dataset_id,
        original_filename=file.filename or "upload.csv",
        detected_encoding=encoding,
        detected_delimiter=delimiter,
        has_header=True,
        columns=columns,
        preview_rows=preview_rows,
        raw_file_bytes=raw_bytes,
    )


@router.post("/{dataset_id}/preview", response_model=UploadResponse)
def repreview_dataset(
    dataset_id: str, config: ImportConfig, user: dict = Depends(require_permission("datasets.upload"))
) -> UploadResponse:
    """Re-run the preview after the user overrides encoding/delimiter/header in the wizard."""
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    try:
        src = ingestion.find_raw_path(dataset_id)
        columns, preview_rows = ingestion.read_preview(
            src, config.encoding, config.delimiter, config.has_header, settings.preview_row_limit
        )
    except _BAD_IMPORT_CONFIG_ERRORS as exc:
        raise HTTPException(400, f"Could not read the file with this encoding/delimiter: {exc}") from exc
    catalog.update_dataset(
        dataset_id,
        encoding=config.encoding,
        delimiter=config.delimiter,
        has_header=config.has_header,
        columns_json=columns,
    )
    return UploadResponse(
        dataset_id=dataset_id,
        original_filename=row["original_filename"],
        detected_encoding=config.encoding,
        detected_delimiter=config.delimiter,
        has_header=config.has_header,
        columns=columns,
        preview_rows=preview_rows,
        raw_file_bytes=src.stat().st_size,
    )


@router.post("/{dataset_id}/import", response_model=JobOut)
def start_import(
    dataset_id: str, config: ImportConfig, user: dict = Depends(require_permission("datasets.upload"))
) -> JobOut:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")

    admin_db.log_activity(
        user, "dataset.imported", "dataset", dataset_id, row.get("original_filename") or "",
        f"encoding={config.encoding}, delimiter={config.delimiter!r}",
    )
    job_id = catalog.create_job(dataset_id, "import")
    submit(
        ingestion.run_import_job,
        dataset_id,
        job_id,
        config.encoding,
        config.delimiter,
        config.has_header,
    )
    return JobOut(id=job_id, dataset_id=dataset_id, kind="import", status="pending", progress="")


@router.get("", response_model=list[DatasetOut])
def list_datasets(user: dict = Depends(get_current_user)) -> list[DatasetOut]:
    return [_dataset_out(r) for r in catalog.list_datasets()]


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, user: dict = Depends(get_current_user)) -> DatasetOut:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    return _dataset_out(row)


@router.get("/{dataset_id}/quality", response_model=QualityReport)
def get_quality(dataset_id: str, user: dict = Depends(get_current_user)) -> QualityReport:
    """The stored report. 404 until one has been produced - datasets imported before
    this existed have none until the report is requested."""
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    raw = row.get("quality_json")
    if not raw:
        raise HTTPException(404, "No quality report yet")
    try:
        return QualityReport(**json.loads(raw))
    except (TypeError, ValueError) as exc:
        raise HTTPException(500, f"Stored quality report is unreadable: {exc}") from exc


@router.post("/{dataset_id}/quality", response_model=JobOut)
def start_quality(
    dataset_id: str, user: dict = Depends(require_permission("datasets.view"))
) -> JobOut:
    """Re-runs the analysis. It reads the whole original file, so it runs as a job."""
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    if row["status"] != "ready":
        raise HTTPException(409, f"Dataset is not ready (status={row['status']})")

    job_id = catalog.create_job(dataset_id, "quality")
    submit(quality.run_quality_job, dataset_id, job_id)
    return JobOut(id=job_id, dataset_id=dataset_id, kind="quality", status="pending", progress="")


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, user: dict = Depends(require_permission("datasets.delete"))) -> dict:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(404, "Dataset not found")
    dataset_connections.delete(dataset_id)
    catalog.delete_dataset(dataset_id)
    upload_dir = ingestion.dataset_upload_dir(dataset_id)
    for f in upload_dir.glob("*"):
        f.unlink(missing_ok=True)
    if upload_dir.exists():
        upload_dir.rmdir()
    admin_db.log_activity(
        user, "dataset.deleted", "dataset", dataset_id, row.get("original_filename") or ""
    )
    return {"deleted": True}
