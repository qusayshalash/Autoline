from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Roles are rows in the database now, so the slug is a free-form string validated
# against the roles table rather than a fixed literal.
Role = str
UserStatus = Literal["active", "inactive", "suspended", "pending"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    id: str
    username: str
    full_name: str = ""
    email: str = ""
    role: Role
    status: UserStatus = "active"
    is_active: bool
    last_login_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MeOut(UserOut):
    """The signed-in user, plus the permissions their role grants. The frontend uses
    these to decide what to render; the backend still enforces them independently."""

    permissions: list[str] = []


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=256)
    role: Role
    full_name: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=180)
    status: UserStatus = "active"


class UpdateUserRequest(BaseModel):
    role: Optional[Role] = None
    status: Optional[UserStatus] = None
    full_name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=180)
    password: Optional[str] = Field(default=None, min_length=6, max_length=256)


# ---- roles & permissions ----

class PermissionOut(BaseModel):
    key: str
    module: str
    action: str


class RoleSummary(BaseModel):
    slug: str
    name: str
    description: str = ""
    is_system: bool = False
    user_count: int = 0
    permission_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RoleDetail(RoleSummary):
    permissions: list[str] = []


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=240)
    permissions: list[str] = []


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    description: Optional[str] = Field(default=None, max_length=240)
    permissions: Optional[list[str]] = None


# ---- activity & overview ----

class ActivityItem(BaseModel):
    id: str
    at: Optional[str] = None
    actor_id: str = ""
    actor_username: str = ""
    action: str
    target_type: str = ""
    target_id: str = ""
    target_label: str = ""
    detail: str = ""


class ActivityPage(BaseModel):
    items: list[ActivityItem]
    total: int


class OverviewOut(BaseModel):
    users_total: int
    users_active: int
    users_by_status: dict[str, int]
    roles_total: int
    permissions_total: int
    languages_enabled: int
    files_total: int
    files_bytes: int
    files_rows: int
    last_activity: Optional[ActivityItem] = None


class LanguageOut(BaseModel):
    code: str
    name: str
    native_name: str
    direction: Literal["rtl", "ltr"]
    enabled: bool
    is_default: bool


class UpdateLanguagesRequest(BaseModel):
    enabled: Optional[list[str]] = None
    default: Optional[str] = None


class SystemStatusOut(BaseModel):
    status: str
    data_dir: str
    storage_bytes: int
    uploads_bytes: int
    datasets_bytes: int
    exports_bytes: int
    dataset_count: int
    started_at: str
    uptime_seconds: int


# ---- import quality ----

class QualityFinding(BaseModel):
    """A single observation. `code` is translated by the frontend, so the wording lives
    with the other translations rather than being frozen in English here."""

    level: Literal["problem", "warning", "info"]
    code: str
    count: Optional[int] = None
    column: Optional[str] = None
    expected: Optional[int] = None
    in_file: Optional[int] = None
    loaded: Optional[int] = None
    bytes: Optional[int] = None
    pct: Optional[float] = None


class QualityDamage(BaseModel):
    row: int
    column: str
    value: str
    byte_offset: int
    byte: str


class QualityColumn(BaseModel):
    name: str
    filled: int
    missing: int
    fill_pct: float
    distinct: int
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    zero_padded: int = 0


class QualityReport(BaseModel):
    generated_at: str
    duration_ms: float
    verdict: Literal["clean", "warning", "problem"]
    source_file: dict
    rows: dict
    structure: dict
    encoding_issues: dict
    columns: list[QualityColumn]
    findings: list[QualityFinding]


# ---- storage ----

class StorageCategory(BaseModel):
    key: str
    bytes: int
    files: int
    removable: bool


class StorageCandidate(BaseModel):
    path: str
    category: str
    bytes: int
    modified: str
    age_hours: float
    reason: str


class StorageOverview(BaseModel):
    data_dir: str
    total_bytes: int
    # 0 means retention is off - nothing expires on its own
    retention_hours: int
    suggested_retention_hours: int = 24
    categories: list[StorageCategory]
    reclaimable_bytes: int
    reclaimable_files: int
    uploads_bytes: int
    disk_free_bytes: int


class StorageCleanupRequest(BaseModel):
    """What to remove. Originals and databases are never eligible, whatever is set."""

    expired_exports: bool = True
    all_exports: bool = False
    intermediates: bool = True


class StorageCleanupResult(BaseModel):
    removed_files: int
    freed_bytes: int
    failed: list[str] = []


class CompactionOut(BaseModel):
    """What a compaction run reclaimed, or why it did not run."""

    dataset_id: str
    bytes_before: int
    bytes_after: int
    freed_bytes: int
    tables: dict[str, int] = {}
    duration_s: float = 0
    # true when the file was already compact - the original is never touched in that case
    skipped: bool = False
    reason: str = ""


class CompactionEstimate(BaseModel):
    dataset_id: str
    file_bytes: int
    tables: dict[str, int] = {}


class LockoutOut(BaseModel):
    """One login counter currently holding attempts off."""

    key: str
    kind: str          # user | ip
    subject: str
    failures: int
    first_failure_at: str
    last_failure_at: str
    locked_until: str
    retry_after_s: int


class BackupItem(BaseModel):
    """One file inside a backup, with what it was found to contain."""

    kind: str                       # catalog | dataset | key | original
    file: str
    bytes: int
    dataset_id: Optional[str] = None
    name: str = ""
    tables: dict[str, int] = {}


class BackupOut(BaseModel):
    name: str
    created_at: str
    duration_s: float = 0
    include_originals: bool = False
    same_disk_as_data: bool = True
    total_bytes: int = 0
    # recomputed from disk on every listing, so a backup damaged after it was written
    # stops reporting the size it had when it was
    bytes_on_disk: int = 0
    items: list[BackupItem] = []
    # every table was read back and matched the counts taken while snapshotting
    verified: bool = False
    intact: bool = False
    errors: list[str] = []


class BackupSummary(BaseModel):
    backup_dir: str
    # a copy on the same disk survives a bad cleaning run, not a dead disk
    same_disk_as_data: bool
    keep: int
    count: int
    verified_count: int
    total_bytes: int
    latest_at: str
    latest_verified: bool
    disk_free_bytes: int


class BackupRequest(BaseModel):
    # the originals are large and usually still on the machine they were uploaded from,
    # so they are opt-in rather than assumed
    include_originals: bool = False


class BackupPruneResult(BaseModel):
    removed: int
    freed_bytes: int


class RetentionRequest(BaseModel):
    # 0 disables expiry entirely
    hours: int = Field(ge=0, le=24 * 365)


class UploadResponse(BaseModel):
    dataset_id: str
    original_filename: str
    detected_encoding: str
    detected_delimiter: str
    has_header: bool
    columns: list[str]
    preview_rows: list[list[str]]
    raw_file_bytes: int


class ImportConfig(BaseModel):
    encoding: str
    delimiter: str
    has_header: bool = True


class DatasetOut(BaseModel):
    id: str
    original_filename: str
    status: str
    error_message: Optional[str] = None
    encoding: Optional[str] = None
    delimiter: Optional[str] = None
    has_header: Optional[bool] = None
    columns: list[str] = []
    row_count_raw: Optional[int] = None
    row_count_cleaned: Optional[int] = None
    raw_file_bytes: Optional[int] = None
    cleaned_file_bytes: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # summary of the import-quality report, so a list can flag a bad file without
    # fetching the whole report for every row
    quality_verdict: Optional[str] = None


class JobOut(BaseModel):
    id: str
    dataset_id: str
    kind: str
    status: str
    progress: str
    result: Optional[dict] = None
    error_message: Optional[str] = None


FilterOp = Literal[
    "eq",
    "neq",
    "contains",
    "starts_with",
    "ends_with",
    "gt",
    "gte",
    "lt",
    "lte",
    "is_null",
    "not_null",
    "in",
]


class FilterRule(BaseModel):
    column: str
    op: FilterOp
    value: Optional[Any] = None
    values: Optional[list[str]] = None  # used only when op == "in"


class DistinctValueItem(BaseModel):
    value: str
    count: int


class DistinctValuesOut(BaseModel):
    column: str
    values: list[DistinctValueItem]
    total_distinct: int
    truncated: bool


class CleaningConfig(BaseModel):
    keep_columns: Optional[list[str]] = None  # None = keep all
    dedupe: bool = False
    dedupe_key_columns: Optional[list[str]] = None  # None with dedupe=True = full-row distinct
    filters: list[FilterRule] = []


class CleaningResult(BaseModel):
    rows_before: int
    rows_after: int
    duplicates_removed: int
    filtered_out: int
    columns_dropped: list[str]
    cleaned_file_bytes: int
    raw_file_bytes: int
    reduction_pct: float


class DataQuery(BaseModel):
    page: int = 1
    page_size: int = 100
    sort_by: Optional[str] = None
    sort_dir: Literal["asc", "desc"] = "asc"
    search: Optional[str] = None
    filters: list[FilterRule] = []
    source: Literal["raw", "cleaned"] = "cleaned"


class DataPage(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total_rows: int
    page: int
    page_size: int
    # wall-clock time DuckDB spent on the count + page queries, in milliseconds
    duration_ms: float = 0.0


class GroupQuery(BaseModel):
    """One level of a group-by tree. `filters` carries both the view's own filters and
    the parent groups' values when drilling into a nested level."""

    column: str
    page: int = 1
    page_size: int = 100
    search: Optional[str] = None
    filters: list[FilterRule] = []
    source: Literal["raw", "cleaned"] = "cleaned"


class GroupItem(BaseModel):
    value: Optional[str]
    count: int


class GroupPage(BaseModel):
    column: str
    groups: list[GroupItem]
    total_groups: int
    page: int
    page_size: int
    duration_ms: float = 0.0


ColumnKind = Literal["text", "number", "date", "category"]


class ColumnInfo(BaseModel):
    name: str
    kind: ColumnKind


class ColumnsOut(BaseModel):
    columns: list[ColumnInfo]


class StatsOut(BaseModel):
    row_count_raw: int
    row_count_cleaned: Optional[int]
    duplicates_removed: int
    filtered_out: int
    raw_file_bytes: int
    cleaned_file_bytes: Optional[int]
    reduction_pct: Optional[float]
    columns: list[str]


class StatisticsQuery(BaseModel):
    """One breakdown request: which column to split by, over which subset."""

    group_by: str
    filters: list[FilterRule] = []
    search: Optional[str] = None
    source: Literal["raw", "cleaned"] = "cleaned"
    limit: int = Field(default=50, ge=1, le=200)
    # how ties between buckets are ordered: by popularity, or by the value itself
    # (chronological for years and months)
    sort: Literal["count", "value"] = "count"
    # date columns only
    granularity: Literal["year", "month", "day"] = "year"
    # numeric histograms only
    bins: int = Field(default=20, ge=2, le=100)


class BreakdownItem(BaseModel):
    value: str
    count: int
    percentage: float
    # NULL or empty in the source - the frontend labels these "unspecified"
    unspecified: bool = False
    # the synthetic bucket holding everything past `limit`
    other: bool = False
    # histogram buckets carry their real range so the chart can label the axis
    bucket_min: Optional[float] = None
    bucket_max: Optional[float] = None


class NumericSummary(BaseModel):
    count: int
    min: float
    max: float
    avg: float
    median: Optional[float] = None


class StatisticsOut(BaseModel):
    group_by: str
    kind: ColumnKind
    mode: Literal["value", "date", "histogram"] = "value"
    # rows matching the filters, and rows in the whole file - the two denominators the
    # dashboard needs ("72% of these" vs "3% of the file")
    total: int
    grand_total: int
    items: list[BreakdownItem]
    distinct_values: int
    truncated: bool
    numeric: Optional[NumericSummary] = None
    execution_ms: float = 0.0


class ColumnSuggestion(BaseModel):
    name: str
    kind: ColumnKind
    approx_distinct: int
    sampled_rows: int


# ---- cross-tab ----

class PivotQuery(BaseModel):
    """A two-dimensional breakdown: one column down the side, one across the top."""

    row_column: str
    column_column: str
    filters: list[FilterRule] = []
    search: Optional[str] = None
    source: Literal["raw", "cleaned"] = "cleaned"
    # A matrix wider than a dozen columns stops being readable, and taller than ~50 rows
    # stops being scannable; whatever falls outside is aggregated rather than dropped.
    row_limit: int = Field(default=25, ge=1, le=100)
    column_limit: int = Field(default=12, ge=1, le=30)
    row_granularity: Literal["year", "month", "day"] = "year"
    column_granularity: Literal["year", "month", "day"] = "year"


class PivotHeader(BaseModel):
    value: str
    total: int
    unspecified: bool = False
    other: bool = False


class PivotRow(BaseModel):
    header: PivotHeader
    # one entry per column header, in the same order
    cells: list[int]


class PivotOut(BaseModel):
    row_column: str
    column_column: str
    row_kind: ColumnKind
    column_kind: ColumnKind
    columns: list[PivotHeader]
    rows: list[PivotRow]
    # rows matching the filters, and rows in the whole file
    total: int
    grand_total: int
    distinct_rows: int
    distinct_columns: int
    rows_truncated: bool
    columns_truncated: bool
    execution_ms: float = 0.0


class StatisticsExportRow(BaseModel):
    label: str
    count: int
    percentage: float


class StatisticsExportRequest(BaseModel):
    """A finished breakdown, ready to be written to a file.

    The rows come from the client rather than being recomputed here so the export is
    exactly what the screen showed - same labels in the same language, same hidden
    categories, same ordering. The figures themselves were produced by /statistics a
    moment earlier; this endpoint only formats them.
    """

    format: Literal["csv", "xlsx", "pdf"]
    title: str = Field(default="", max_length=200)
    subtitle: str = Field(default="", max_length=400)
    headers: list[str] = Field(default_factory=lambda: ["Value", "Count", "Percentage"])
    rows: list[StatisticsExportRow] = Field(default_factory=list, max_length=1000)
    total_label: str = Field(default="Total", max_length=80)
    total: int = 0


class ExportRequest(BaseModel):
    format: Literal["csv", "xlsx", "pdf"]
    scope: Literal["all", "current_view"] = "all"
    source: Literal["raw", "cleaned"] = "cleaned"
    search: Optional[str] = None
    filters: list[FilterRule] = []
    sort_by: Optional[str] = None
    sort_dir: Literal["asc", "desc"] = "asc"
