import axios from "axios";

import i18n from "../i18n";

export const api = axios.create({
  baseURL: "http://localhost:8000/api",
  withCredentials: true,
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const url: string = error?.config?.url ?? "";
    if (error?.response?.status === 401 && !url.includes("/auth/") && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    // The permission list AuthContext holds is fetched once and cached; a 403 means it
    // is already wrong (a role change landed on the server since), so the tab is told to
    // re-fetch it rather than waiting for the next scheduled refresh.
    if (error?.response?.status === 403) {
      window.dispatchEvent(new Event("auth:forbidden"));
    }
    return Promise.reject(error);
  }
);

/** Turns a failed request into something worth showing somebody.
 *
 * Three sources, in order. The error's `code` if we have a translation for it - that is
 * the only one that comes out in the reader's language, and it is why the API sends a
 * code beside the sentence at all. Then the backend's own `detail`, which is English and
 * is what the errors carrying a column name or a parser's complaint still fall back to.
 * Then the caller's generic line, for failures that never reached the API: a dropped
 * connection, a validation error's list-shaped detail.
 *
 * Use this rather than `(err as Error).message`, which only ever yields "Request failed
 * with status code 400".
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: { detail?: unknown; code?: unknown } } })
    ?.response?.data;

  const code = data?.code;
  if (typeof code === "string" && code) {
    const translated = i18n.t(`errors.${code}`, { defaultValue: "" });
    if (translated) return translated;
  }

  const detail = data?.detail;
  if (typeof detail === "string" && detail) return detail;
  return fallback;
}

export type FilterOp =
  | "eq"
  | "neq"
  | "contains"
  | "starts_with"
  | "ends_with"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "is_null"
  | "not_null"
  | "in";

export interface FilterRule {
  column: string;
  op: FilterOp;
  value?: string | null;
  values?: string[] | null;
}

/** The blank rule a "+ Add filter" button appends. Lives here rather than in
 *  FilterBuilder so both that component and the Explorer toolbar (which hosts its own
 *  add button) start from the same shape. */
export function newFilter(columns: string[]): FilterRule {
  return { column: columns[0] ?? "", op: "eq", value: "" };
}

export interface DistinctValueItem {
  value: string;
  count: number;
}

export interface DistinctValuesOut {
  column: string;
  values: DistinctValueItem[];
  total_distinct: number;
  truncated: boolean;
}

export interface Dataset {
  id: string;
  original_filename: string;
  status: string;
  error_message?: string | null;
  encoding?: string | null;
  delimiter?: string | null;
  has_header?: boolean | null;
  columns: string[];
  row_count_raw?: number | null;
  row_count_cleaned?: number | null;
  raw_file_bytes?: number | null;
  cleaned_file_bytes?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  /** summary of the import-quality report, present once one has been produced */
  quality_verdict?: QualityVerdict | null;
  /**
   * Which columns identify a record, empty until an administrator says.
   *
   * Nothing in an imported table identifies a row on its own, so until this is set a
   * later batch can only be added to the end and a cell cannot be corrected. The
   * screens read it to say so, rather than offering a control that would fail.
   */
  key_columns: string[];
}

export type QualityVerdict = "clean" | "warning" | "problem";

export interface QualityFinding {
  level: "problem" | "warning" | "info";
  code: string;
  count?: number | null;
  column?: string | null;
  expected?: number | null;
  in_file?: number | null;
  loaded?: number | null;
  bytes?: number | null;
  pct?: number | null;
}

export interface QualityColumn {
  name: string;
  filled: number;
  missing: number;
  fill_pct: number;
  distinct: number;
  min_length: number | null;
  max_length: number | null;
  zero_padded: number;
}

export interface QualityDamage {
  row: number;
  column: string;
  value: string;
  byte_offset: number;
  byte: string;
}

export interface QualityReport {
  generated_at: string;
  duration_ms: number;
  verdict: QualityVerdict;
  source_file: {
    name: string | null;
    bytes: number | null;
    available: boolean;
    encoding: string;
    delimiter: string;
  };
  rows: { in_file: number | null; loaded: number; duplicates: number };
  structure: { columns: number; field_count_spread: Record<string, number> };
  encoding_issues: {
    undecodable_bytes: number;
    damaged_values: number;
    samples: QualityDamage[];
  };
  columns: QualityColumn[];
  findings: QualityFinding[];
}

/** The stored report, or null when the dataset has never been analysed. */
export async function fetchQualityReport(datasetId: string): Promise<QualityReport | null> {
  try {
    const { data } = await api.get<QualityReport>(`/datasets/${datasetId}/quality`);
    return data;
  } catch (err) {
    if ((err as { response?: { status?: number } })?.response?.status === 404) return null;
    throw err;
  }
}

/** Starts a fresh analysis. It reads the whole original file, so it returns a job. */
export async function startQualityReport(datasetId: string): Promise<JobOut> {
  const { data } = await api.post<JobOut>(`/datasets/${datasetId}/quality`, {});
  return data;
}

export interface UploadResponse {
  dataset_id: string;
  original_filename: string;
  detected_encoding: string;
  detected_delimiter: string;
  has_header: boolean;
  columns: string[];
  preview_rows: string[][];
  raw_file_bytes: number;
}

export interface JobOut {
  id: string;
  dataset_id: string;
  kind: string;
  status: "pending" | "running" | "cancelling" | "cancelled" | "done" | "error";
  progress: string;
  result?: Record<string, unknown> | null;
  error_message?: string | null;
}

export interface DataPage {
  columns: string[];
  rows: unknown[][];
  total_rows: number;
  page: number;
  page_size: number;
  /** time DuckDB spent on the query, reported by the server */
  duration_ms: number;
  /** full round-trip measured in the browser; added by fetchData, not by the API */
  elapsed_ms?: number;
  /**
   * "new", "updated" or null for each row, parallel to `rows`.
   *
   * Only populated when the dataset has a record key and a batch arrived inside the
   * marking window; otherwise every entry is null.
   */
  arrivals: (Arrival | null)[];
}

export interface StatsOut {
  row_count_raw: number;
  row_count_cleaned: number | null;
  duplicates_removed: number;
  filtered_out: number;
  raw_file_bytes: number;
  cleaned_file_bytes: number | null;
  reduction_pct: number | null;
  columns: string[];
}

export interface CleaningConfig {
  keep_columns?: string[] | null;
  dedupe: boolean;
  dedupe_key_columns?: string[] | null;
  filters: FilterRule[];
}

export interface CleaningResult {
  rows_before: number;
  rows_after: number;
  duplicates_removed: number;
  filtered_out: number;
  columns_dropped: string[];
  cleaned_file_bytes: number;
  raw_file_bytes: number;
  reduction_pct: number;
}

export async function uploadDataset(file: File, onProgress?: (pct: number) => void): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<UploadResponse>("/datasets/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (evt) => {
      if (onProgress && evt.total) onProgress(Math.round((evt.loaded / evt.total) * 100));
    },
  });
  return data;
}

export async function repreviewDataset(
  datasetId: string,
  config: { encoding: string; delimiter: string; has_header: boolean }
): Promise<UploadResponse> {
  const { data } = await api.post<UploadResponse>(`/datasets/${datasetId}/preview`, config);
  return data;
}

export async function startImport(
  datasetId: string,
  config: { encoding: string; delimiter: string; has_header: boolean }
): Promise<JobOut> {
  const { data } = await api.post<JobOut>(`/datasets/${datasetId}/import`, config);
  return data;
}

export async function listDatasets(): Promise<Dataset[]> {
  const { data } = await api.get<Dataset[]>("/datasets");
  return data;
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  const { data } = await api.get<Dataset>(`/datasets/${datasetId}`);
  return data;
}

export async function deleteDataset(datasetId: string): Promise<void> {
  await api.delete(`/datasets/${datasetId}`);
}

export async function renameDataset(datasetId: string, name: string): Promise<Dataset> {
  const { data } = await api.patch<Dataset>(`/datasets/${datasetId}`, { name });
  return data;
}

export async function getJob(jobId: string): Promise<JobOut> {
  const { data } = await api.get<JobOut>(`/jobs/${jobId}`);
  return data;
}

export async function cancelJob(jobId: string): Promise<JobOut> {
  const { data } = await api.post<JobOut>(`/jobs/${jobId}/cancel`, {});
  return data;
}

export async function fetchData(
  datasetId: string,
  params: {
    page: number;
    page_size: number;
    sort_by?: string | null;
    sort_dir?: "asc" | "desc";
    search?: string | null;
    /** which columns the search looks in; omitted or empty means all of them */
    search_columns?: string[];
    filters?: FilterRule[];
    source?: "raw" | "cleaned";
    /** keep only records a recent batch brought */
    only_recent?: boolean;
  }
): Promise<DataPage> {
  // `duration_ms` from the server is the query time alone; timing the call here adds
  // transfer and parsing, which is what the user actually waits for.
  const started = performance.now();
  const { data } = await api.post<DataPage>(`/datasets/${datasetId}/data`, {
    page: params.page,
    page_size: params.page_size,
    sort_by: params.sort_by ?? null,
    sort_dir: params.sort_dir ?? "asc",
    search: params.search ?? null,
    search_columns: params.search_columns ?? [],
    filters: params.filters ?? [],
    source: params.source ?? "cleaned",
    only_recent: params.only_recent ?? false,
  });
  return { ...data, elapsed_ms: Math.round(performance.now() - started) };
}

export interface GroupItem {
  value: string | null;
  count: number;
}

export interface GroupPage {
  column: string;
  groups: GroupItem[];
  total_groups: number;
  page: number;
  page_size: number;
  duration_ms: number;
}

/** Fetches one level of a group-by tree. Nesting is expressed by passing the parent
 *  groups' values as extra equality filters, so this same call serves every level. */
export async function fetchGroups(
  datasetId: string,
  params: {
    column: string;
    page?: number;
    page_size?: number;
    search?: string | null;
    search_columns?: string[];
    filters?: FilterRule[];
    source?: "raw" | "cleaned";
  }
): Promise<GroupPage> {
  const { data } = await api.post<GroupPage>(`/datasets/${datasetId}/group`, {
    column: params.column,
    page: params.page ?? 1,
    page_size: params.page_size ?? 100,
    search: params.search ?? null,
    search_columns: params.search_columns ?? [],
    filters: params.filters ?? [],
    source: params.source ?? "cleaned",
  });
  return data;
}

/** Equality filters that pin a group path, e.g. kinuy_mishari = "COROLLA". Empty group
 *  values are stored as "" in the table, so they compare with eq like any other value. */
export function groupPathFilters(path: { column: string; value: string | null }[]): FilterRule[] {
  return path.map(({ column, value }) =>
    value === null ? { column, op: "is_null" as const } : { column, op: "eq" as const, value }
  );
}

export type ColumnKind = "text" | "number" | "date" | "category";

export interface ColumnInfo {
  name: string;
  kind: ColumnKind;
}

export async function fetchColumns(
  datasetId: string,
  source: "raw" | "cleaned"
): Promise<ColumnInfo[]> {
  const { data } = await api.get<{ columns: ColumnInfo[] }>(`/datasets/${datasetId}/columns`, {
    params: { source },
  });
  return data.columns;
}

export async function fetchDistinctValues(
  datasetId: string,
  params: { column: string; search?: string | null; source?: "raw" | "cleaned"; limit?: number }
): Promise<DistinctValuesOut> {
  const { data } = await api.get<DistinctValuesOut>(`/datasets/${datasetId}/data/distinct-values`, {
    params: {
      column: params.column,
      search: params.search || undefined,
      source: params.source ?? "cleaned",
      limit: params.limit,
    },
  });
  return data;
}

export async function getStats(datasetId: string): Promise<StatsOut> {
  const { data } = await api.get<StatsOut>(`/datasets/${datasetId}/stats`);
  return data;
}

export async function applyCleaning(datasetId: string, config: CleaningConfig): Promise<CleaningResult> {
  const { data } = await api.post<CleaningResult>(`/datasets/${datasetId}/clean`, config);
  return data;
}

/* --- which columns identify a record ------------------------------------------------ */

export interface KeyCheck {
  columns: string[];
  total_rows: number;
  distinct_keys: number;
  duplicate_rows: number;
  blank_keys: number;
  unique: boolean;
}

/** Counts what these columns would identify, without setting anything. */
export async function checkDatasetKey(datasetId: string, columns: string[]): Promise<KeyCheck> {
  const { data } = await api.get<KeyCheck>(`/datasets/${datasetId}/key/check`, {
    params: { columns: columns.join(",") },
  });
  return data;
}

export async function setDatasetKey(datasetId: string, columns: string[]): Promise<Dataset> {
  const { data } = await api.put<Dataset>(`/datasets/${datasetId}/key`, { columns });
  return data;
}

export async function clearDatasetKey(datasetId: string): Promise<Dataset> {
  const { data } = await api.delete<Dataset>(`/datasets/${datasetId}/key`);
  return data;
}

/* --- a later batch of the same data -------------------------------------------------- */

export interface AppendResult {
  rows_added: number;
  rows_replaced: number;
  row_count_raw: number;
  cleaned_rebuilt: boolean;
}

/**
 * Adds a later file of the same shape to a dataset that already exists.
 *
 * Encoding and delimiter are left to the server, which uses the dataset's own rather
 * than detecting them again - a small batch does not carry enough evidence to detect
 * anything reliably. They are passed only when the caller knows this batch differs.
 */
export async function appendBatch(
  datasetId: string,
  file: File,
  options?: { encoding?: string; delimiter?: string },
  onProgress?: (pct: number) => void
): Promise<AppendResult> {
  const form = new FormData();
  form.append("file", file);
  if (options?.encoding) form.append("encoding", options.encoding);
  if (options?.delimiter) form.append("delimiter", options.delimiter);
  const { data } = await api.post<AppendResult>(`/datasets/${datasetId}/append`, form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (evt) => {
      if (onProgress && evt.total) onProgress(Math.round((evt.loaded / evt.total) * 100));
    },
  });
  return data;
}

/* --- what arrived recently ------------------------------------------------------- */

/** "new" if the record was not here before the batch, "updated" if it was. */
export type Arrival = "new" | "updated";

export interface ArrivalSummary {
  new: number;
  updated: number;
  latest_at?: string | null;
  window_days: number;
}

/**
 * What a recent batch brought, or null when none has.
 *
 * Null rather than zeros: the screen uses it to decide whether to offer the filter at
 * all, and "no batch has landed here" is a different thing from "one landed and brought
 * nothing".
 */
export async function fetchArrivals(datasetId: string): Promise<ArrivalSummary | null> {
  const { data } = await api.get<ArrivalSummary | null>(`/datasets/${datasetId}/arrivals`);
  return data;
}

export async function setArrivalWindow(days: number): Promise<{ days: number }> {
  const { data } = await api.put<{ days: number }>("/datasets/arrivals/window", { days });
  return data;
}

/* --- correcting a record -------------------------------------------------------------- */

export interface Correction {
  row_key: string[];
  column: string;
  old_value?: string | null;
  new_value?: string | null;
  actor?: string | null;
  edited_at?: string | null;
}

export interface RowEditResult {
  columns: string[];
  row: (string | null)[];
  corrections: Correction[];
}

/** `key` is positional against the dataset's key_columns, in that order. */
export async function editRow(
  datasetId: string,
  key: string[],
  changes: Record<string, string>
): Promise<RowEditResult> {
  const { data } = await api.patch<RowEditResult>(`/datasets/${datasetId}/rows`, { key, changes });
  return data;
}

/** Puts the file's own value back. The values in `columns` are ignored by the server. */
export async function revertCorrection(
  datasetId: string,
  key: string[],
  columns: string[]
): Promise<RowEditResult> {
  const changes = Object.fromEntries(columns.map((c) => [c, ""]));
  const { data } = await api.delete<RowEditResult>(`/datasets/${datasetId}/corrections`, {
    data: { key, changes },
  });
  return data;
}

export async function fetchCorrections(
  datasetId: string,
  limit = 200,
  offset = 0
): Promise<{ total: number; items: Correction[] }> {
  const { data } = await api.get<{ total: number; items: Correction[] }>(
    `/datasets/${datasetId}/corrections`,
    { params: { limit, offset } }
  );
  return data;
}

export interface ExportRequest {
  format: "csv" | "xlsx" | "pdf";
  scope: "all" | "current_view";
  source: "raw" | "cleaned";
  search?: string | null;
  search_columns?: string[];
  filters?: FilterRule[];
  sort_by?: string | null;
  sort_dir?: "asc" | "desc";
}

export async function requestExport(datasetId: string, req: ExportRequest): Promise<JobOut> {
  const { data } = await api.post<JobOut>(`/datasets/${datasetId}/export`, req);
  return data;
}

export function downloadExportUrl(datasetId: string, jobId: string): string {
  return `${api.defaults.baseURL}/datasets/${datasetId}/export/${jobId}/download`;
}

/** Roles are rows in the database, so this is a slug rather than a closed set. */
export type Role = string;

export interface User {
  id: string;
  username: string;
  full_name?: string;
  email?: string;
  role: Role;
  status?: "active" | "inactive" | "suspended" | "pending";
  is_active: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  /** permissions granted by the user's role, resolved server-side on every request */
  permissions?: string[];
}

export async function login(username: string, password: string): Promise<User> {
  const { data } = await api.post<User>("/auth/login", { username, password });
  return data;
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}

export async function getMe(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}

export async function listUsers(): Promise<User[]> {
  const { data } = await api.get<User[]>("/users");
  return data;
}

export async function createUser(body: { username: string; password: string; role: Role }): Promise<User> {
  const { data } = await api.post<User>("/users", body);
  return data;
}

export async function updateUser(
  userId: string,
  body: { role?: Role; is_active?: boolean; password?: string }
): Promise<User> {
  const { data } = await api.patch<User>(`/users/${userId}`, body);
  return data;
}

export async function deleteUser(userId: string): Promise<void> {
  await api.delete(`/users/${userId}`);
}

// ---- column profiling ----

export interface ProfileColumnSummary {
  name: string;
  filled: number;
  missing: number;
  fill_pct: number;
  /** approximate - the exact count is in that column's own profile */
  approx_distinct: number;
}

export interface ProfileOverview {
  source: string;
  total: number;
  columns: ProfileColumnSummary[];
  execution_ms: number;
}

export interface ProfileValue {
  value: string;
  count: number;
  pct: number;
  blank: boolean;
}

export interface ProfileLength {
  length: number;
  count: number;
  pct: number;
}

export interface ProfileNumeric {
  count: number;
  not_numeric: number;
  min: number;
  max: number;
  avg: number | null;
  q1: number | null;
  median: number | null;
  q3: number | null;
  outlier_low: number | null;
  outlier_high: number | null;
  outliers: number;
}

export interface ProfileFinding {
  level: "problem" | "note";
  code: string;
  count?: number | null;
  pct?: number | null;
  missing?: number | null;
  distinct?: number | null;
  length?: number | null;
  low?: number | null;
  high?: number | null;
}

export interface ColumnProfile {
  column: string;
  kind: ColumnKind;
  source: string;
  total: number;
  filled: number;
  missing: number;
  fill_pct: number;
  distinct: number;
  distinct_pct: number;
  min_length: number | null;
  max_length: number | null;
  zero_padded: number;
  top_values: ProfileValue[];
  lengths: ProfileLength[];
  numeric: ProfileNumeric | null;
  findings: ProfileFinding[];
  execution_ms: number;
}

export async function fetchProfileOverview(
  datasetId: string,
  source: "raw" | "cleaned" = "cleaned"
): Promise<ProfileOverview> {
  const { data } = await api.get<ProfileOverview>(`/datasets/${datasetId}/profile`, {
    params: { source },
  });
  return data;
}

export async function fetchColumnProfile(
  datasetId: string,
  column: string,
  source: "raw" | "cleaned" = "cleaned"
): Promise<ColumnProfile> {
  const { data } = await api.get<ColumnProfile>(
    `/datasets/${datasetId}/profile/${encodeURIComponent(column)}`,
    { params: { source } }
  );
  return data;
}
