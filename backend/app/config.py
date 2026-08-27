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

    # ---- session cookie -------------------------------------------------------
    #
    # The cookie is the whole session: whoever holds it is signed in, without a
    # password. It is already httponly (script cannot read it) and SameSite (another
    # site cannot make the browser send it). The third protection is Secure, which
    # tells the browser to withhold it from any connection that is not HTTPS -
    # without it, one plain-http request puts the token on the wire in clear text for
    # anyone sharing the network.
    #
    # It cannot simply default to on: over http://localhost the browser would discard
    # the cookie and nobody could sign in at all. So the value is derived rather than
    # hardcoded - see cookie_is_secure. Setting PUBLIC_ORIGIN to an https:// address
    # turns it on by itself, which is the point: a protection that has to be
    # remembered on deployment day is one that gets left off, and nothing about the
    # app looks broken when it is.
    public_origin: Optional[str] = None

    # Overrides the derivation in both directions. Needed when TLS is terminated by a
    # proxy in front of this process - the app only ever sees http, so it cannot work
    # out on its own that the browser is on https.
    cookie_secure: Optional[bool] = None

    # "lax" suits an API served from the same site as the app. Cross-site needs
    # "none", which browsers accept only alongside Secure - see cookie_is_secure.
    cookie_samesite: str = "lax"

    @property
    def cookie_is_secure(self) -> bool:
        """Whether the session cookie is withheld from plain http.

        Explicit setting first; otherwise inferred from the address the app is served
        on. SameSite=None forces it on regardless, because a browser silently drops
        that combination without Secure - which presents as "login does nothing", with
        no error anywhere to say why.
        """
        if self.cookie_secure is not None:
            return self.cookie_secure
        if self.cookie_samesite.lower() == "none":
            return True
        return (self.public_origin or "").strip().lower().startswith("https://")

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
