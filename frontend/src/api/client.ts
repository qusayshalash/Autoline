import axios from "axios";

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
    return Promise.reject(error);
  }
);

/** Extracts the backend's `{"detail": "..."}` message from a failed request, falling
 * back to a generic message when the error didn't come from our API (network failure,
 * validation error shape, etc). Use this instead of `(err as Error).message`, which
 * only ever shows a generic "Request failed with status code 400" type string. */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
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
  status: "pending" | "running" | "done" | "error";
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

export async function getJob(jobId: string): Promise<JobOut> {
  const { data } = await api.get<JobOut>(`/jobs/${jobId}`);
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
    filters?: FilterRule[];
    source?: "raw" | "cleaned";
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
    filters: params.filters ?? [],
    source: params.source ?? "cleaned",
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
    filters?: FilterRule[];
    source?: "raw" | "cleaned";
  }
): Promise<GroupPage> {
  const { data } = await api.post<GroupPage>(`/datasets/${datasetId}/group`, {
    column: params.column,
    page: params.page ?? 1,
    page_size: params.page_size ?? 100,
    search: params.search ?? null,
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

export interface ExportRequest {
  format: "csv" | "xlsx" | "pdf";
  scope: "all" | "current_view";
  source: "raw" | "cleaned";
  search?: string | null;
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
