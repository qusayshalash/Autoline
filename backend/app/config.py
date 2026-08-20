from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration. Every field can be overridden by an environment variable of
    the same name, or by a line in `backend/.env`.

    `data_dir` is the one that matters most in practice. It holds the DuckDB catalog, the
    per-dataset database files and the uploaded originals - gigabytes of them, written to
    constantly while the app runs. It must point somewhere that no file-syncing client
    watches: a service that copies a `.duckdb` file while DuckDB has it open for writing
    can capture a half-written page, and the database that comes back is corrupt. The
    default below is inside the project, which is fine for a checkout but wrong the moment
    the project itself lives in a synced folder - so a real installation sets DATA_DIR.
    """

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_dir: Path = _BACKEND_DIR / "data"
    upload_chunk_bytes: int = 4 * 1024 * 1024
    detection_sample_bytes: int = 8 * 1024 * 1024
    preview_row_limit: int = 50
    default_page_size: int = 100
    max_page_size: int = 1000
    distinct_values_limit: int = 500
    xlsx_sheet_row_limit: int = 1_000_000  # stay under Excel's 1,048,576 cap
    xlsx_batch_rows: int = 50_000
    pdf_row_limit: int = 10_000
    export_ttl_hours: int = 24

    # A CSV upload is written to data_dir in chunks with no cap on the file's own size -
    # the real registry export this is built against is 867 MB, and a hard byte ceiling
    # would reject legitimate files right along with runaway ones. What is bounded
    # instead is the free space behind it: the write is refused, mid-stream if need be,
    # once continuing would leave less than this much room on the disk. 1 GB leaves
    # headroom for the cleaned-table rewrite cleaning produces, which briefly holds two
    # copies of the table on the same disk.
    min_free_disk_bytes: int = 1_000_000_000

    # Where verified snapshots are written. Defaults next to the data, which protects
    # against the failures that actually happen most - a bad cleaning run, a deleted
    # dataset - but not against the disk itself dying. Point BACKUP_DIR at another drive
    # (or a network share) and it protects against that too; the settings screen says
    # which of the two you currently have.
    backup_dir: Optional[Path] = None
    # How many verified backups to keep. Older ones are pruned after a successful run.
    backup_keep: int = 3

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "catalog.duckdb"

    @property
    def backups_dir(self) -> Path:
        return self.backup_dir or (self.data_dir / "backups")

    def ensure_dirs(self) -> None:
        for d in (self.uploads_dir, self.datasets_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
