import csv
import json

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi import File as FastAPIFile

from app.errors import ApiError
from app.auth import require_permission
from app.services import clocks
from app.config import settings
from app.db import admin as admin_db
from app.db import catalog
from app.db.connection import datasets as dataset_connections
from app.jobs import submit
from app.models.schemas import (
    AppendResult,
    DatasetOut,
    DatasetRenameRequest,
    ImportConfig,
    JobOut,
    KeyCheck,
    KeyColumnsRequest,
    QualityReport,
    UploadResponse,
)
from app.services import appending, corrections, ingestion, quality, row_identity

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
        key_columns=row_identity.key_columns(row),
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
        raise ApiError(404, "dataset_not_found", "Dataset not found")
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
        raise ApiError(404, "dataset_not_found", "Dataset not found")

    admin_db.log_activity(
        user, "dataset.imported", "dataset", dataset_id, row.get("original_filename") or "",
        f"encoding={config.encoding}, delimiter={config.delimiter!r}",
        detail_code="import_config",
        encoding=config.encoding,
        delimiter=config.delimiter,
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
def list_datasets(user: dict = Depends(require_permission("datasets.view"))) -> list[DatasetOut]:
    return [_dataset_out(r) for r in catalog.list_datasets()]


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, user: dict = Depends(require_permission("datasets.view"))) -> DatasetOut:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    return _dataset_out(row)


@router.get("/{dataset_id}/quality", response_model=QualityReport)
def get_quality(dataset_id: str, user: dict = Depends(require_permission("datasets.view"))) -> QualityReport:
    """The stored report. 404 until one has been produced - datasets imported before
    this existed have none until the report is requested."""
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    raw = row.get("quality_json")
    if not raw:
        raise ApiError(404, "quality_report_missing", "No quality report yet")
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
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    if row["status"] != "ready":
        raise HTTPException(409, f"Dataset is not ready (status={row['status']})")

    job_id = catalog.create_job(dataset_id, "quality")
    submit(quality.run_quality_job, dataset_id, job_id)
    return JobOut(id=job_id, dataset_id=dataset_id, kind="quality", status="pending", progress="")


# ---- which columns identify a record -------------------------------------------------

def _ready_dataset(dataset_id: str) -> dict:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    if row.get("status") != "ready":
        raise ApiError(409, "dataset_not_ready", "This dataset has not finished importing")
    return row


def _key_problem(exc: row_identity.KeyProblem) -> ApiError:
    """A refused key is a 422 carrying its numbers, not a bare 400.

    The interface shows the duplicate count in its own language, and the only way it can
    is if the counts travel with the code.
    """
    return ApiError(422, exc.code, str(exc))


@router.get("/{dataset_id}/key/check", response_model=KeyCheck)
def check_key(
    dataset_id: str,
    columns: str,
    user: dict = Depends(require_permission("datasets.edit")),
) -> KeyCheck:
    """Counts what these columns would identify, without setting anything.

    A dry run on purpose: on a four-million-row table an administrator should be able
    to try `plate`, see that 12 rows share one, and try `plate, year` instead - without
    each attempt changing the dataset.
    """
    _ready_dataset(dataset_id)
    wanted = [c for c in columns.split(",") if c.strip()]
    try:
        return KeyCheck(**row_identity.validate(dataset_id, [c.strip() for c in wanted]))
    except row_identity.KeyProblem as exc:
        raise _key_problem(exc) from exc


@router.put("/{dataset_id}/key", response_model=DatasetOut)
def set_key(
    dataset_id: str,
    body: KeyColumnsRequest,
    user: dict = Depends(require_permission("datasets.edit")),
) -> DatasetOut:
    row = _ready_dataset(dataset_id)
    try:
        result = row_identity.require_unique(dataset_id, body.columns)
    except row_identity.KeyProblem as exc:
        raise _key_problem(exc) from exc

    catalog.update_dataset(dataset_id, key_columns_json=body.columns)
    admin_db.log_activity(
        user,
        "dataset.key_set",
        "dataset",
        dataset_id,
        row.get("original_filename") or "",
        f"key: {', '.join(body.columns)}",
        detail_code="key_columns",
        columns=", ".join(body.columns),
        count=result["distinct_keys"],
    )
    return _dataset_out(catalog.get_dataset(dataset_id))


@router.delete("/{dataset_id}/key", response_model=DatasetOut)
def clear_key(
    dataset_id: str, user: dict = Depends(require_permission("datasets.edit"))
) -> DatasetOut:
    """Unsets the key. Existing corrections are kept, not deleted.

    They are addressed by key values, so they simply stop being replayed until a key is
    set again - and throwing away an audit trail because somebody changed their mind
    about a column would be the wrong way round.
    """
    row = _ready_dataset(dataset_id)
    catalog.update_dataset(dataset_id, key_columns_json=None)
    admin_db.log_activity(
        user,
        "dataset.key_cleared",
        "dataset",
        dataset_id,
        row.get("original_filename") or "",
    )
    return _dataset_out(catalog.get_dataset(dataset_id))


# ---- a later batch of the same data ----------------------------------------------------

@router.post("/{dataset_id}/append", response_model=AppendResult)
async def append_batch(
    dataset_id: str,
    file: UploadFile = FastAPIFile(...),
    encoding: str | None = Form(default=None),
    delimiter: str | None = Form(default=None),
    user: dict = Depends(require_permission("datasets.upload")),
) -> AppendResult:
    """Adds a later file of the same shape to a dataset that already exists.

    The dataset's own encoding and delimiter are the default, not a fresh detection.
    That is the premise of appending: this is a later instalment of the same data, so
    the first file already answered the question. Detection on a small batch is also
    actively dangerous - six Hebrew bytes in a 36-byte file are enough for
    charset-normalizer to answer "johab", a Korean codepage, whose multi-byte sequences
    then swallow the delimiter and merge two columns into one. The caller can still say
    otherwise for a batch that genuinely differs.

    Synchronous rather than a background job, deliberately: the answer the uploader
    needs is whether the file was accepted at all, and the column check decides that in
    the first moments. A batch big enough to need a job is a batch that should be its
    own dataset.
    """
    row = _ready_dataset(dataset_id)
    expected = json.loads(row["columns_json"]) if row.get("columns_json") else []
    if not expected:
        raise ApiError(409, "dataset_has_no_columns", "This dataset has no columns yet")

    suffix = "".join(
        ch for ch in ("." + (file.filename or "csv").rsplit(".", 1)[-1]) if ch.isalnum() or ch == "."
    ) or ".csv"
    incoming = ingestion.dataset_upload_dir(dataset_id) / f"incoming{suffix}"
    try:
        with open(incoming, "wb") as out:
            while chunk := await file.read(settings.upload_chunk_bytes):
                out.write(chunk)

        encoding = encoding or row.get("encoding") or ingestion.detect_encoding(incoming)
        delimiter = delimiter or row.get("delimiter") or ingestion.detect_delimiter(
            incoming, encoding
        )
        stored = appending.next_batch_path(dataset_id)
        try:
            added = appending.stage(
                incoming, stored, encoding, delimiter, True, expected
            )
        except Exception:
            stored.unlink(missing_ok=True)  # never leave a half-written batch to replay
            raise
    except appending.AppendProblem as exc:
        raise ApiError(422, exc.code, str(exc)) from exc
    except _BAD_IMPORT_CONFIG_ERRORS as exc:
        raise ApiError(400, "append_unreadable", f"Could not read the file: {exc}") from exc
    finally:
        incoming.unlink(missing_ok=True)

    outcome = appending.apply_batch(dataset_id, stored, row)
    corrections.replay(dataset_id, row)
    rebuilt = appending.rebuild_cleaned(dataset_id) is not None

    total = dataset_connections.cursor(dataset_id).execute(
        "SELECT COUNT(*) FROM raw_data"
    ).fetchone()[0]
    catalog.update_dataset(dataset_id, row_count_raw=total)

    admin_db.log_activity(
        user,
        "dataset.appended",
        "dataset",
        dataset_id,
        row.get("original_filename") or "",
        f"+{added} rows, {outcome['replaced']} replaced",
        detail_code="rows_appended",
        count=added,
        replaced=outcome["replaced"],
    )
    return AppendResult(
        rows_added=added - outcome["replaced"],
        rows_replaced=outcome["replaced"],
        row_count_raw=total,
        cleaned_rebuilt=rebuilt,
    )


@router.patch("/{dataset_id}", response_model=DatasetOut)
def rename_dataset(
    dataset_id: str, body: DatasetRenameRequest, user: dict = Depends(require_permission("datasets.clean"))
) -> DatasetOut:
    """The display name only - never the id, and never anything on disk, both of which
    are keyed off the id precisely so a rename can be this cheap and this safe."""
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    name = body.name.strip()
    if not name:
        raise ApiError(400, "name_empty", "Name cannot be empty")
    old_name = row.get("original_filename") or ""
    catalog.update_dataset(dataset_id, original_filename=name)
    admin_db.log_activity(
        user,
        "dataset.renamed",
        "dataset",
        dataset_id,
        name,
        f"was: {old_name}",
        detail_code="was_named",
        name=old_name,
    )
    return _dataset_out(catalog.get_dataset(dataset_id))


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, user: dict = Depends(require_permission("datasets.delete"))) -> dict:
    row = catalog.get_dataset(dataset_id)
    if row is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
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
