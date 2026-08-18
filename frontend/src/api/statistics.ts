import { api } from "./client";
import type { ColumnKind, FilterRule } from "./client";

/** How the backend split the rows up: by the value itself, by a truncated date, or
 *  into equal-width numeric buckets. */
export type BreakdownMode = "value" | "date" | "histogram";

export type Granularity = "year" | "month" | "day";

export interface BreakdownItem {
  value: string;
  count: number;
  percentage: number;
  /** NULL or empty in the source - shown as "unspecified" rather than dropped */
  unspecified: boolean;
  /** the synthetic bucket holding every value past the requested limit */
  other: boolean;
  bucket_min: number | null;
  bucket_max: number | null;
}

export interface NumericSummary {
  count: number;
  min: number;
  max: number;
  avg: number;
  median: number | null;
}

export interface StatisticsOut {
  group_by: string;
  kind: ColumnKind;
  mode: BreakdownMode;
  /** rows matching the current filters */
  total: number;
  /** rows in the whole file, the denominator for "share of the file" */
  grand_total: number;
  items: BreakdownItem[];
  distinct_values: number;
  truncated: boolean;
  numeric: NumericSummary | null;
  /** time the server spent, in ms, reported by the API */
  execution_ms: number;
  /** full round-trip measured in the browser; added here, not by the API */
  elapsed_ms?: number;
}

export interface ColumnSuggestion {
  name: string;
  kind: ColumnKind;
  approx_distinct: number;
  sampled_rows: number;
}

export interface StatisticsParams {
  group_by: string;
  filters?: FilterRule[];
  search?: string | null;
  source?: "raw" | "cleaned";
  limit?: number;
  sort?: "count" | "value";
  granularity?: Granularity;
  bins?: number;
}

/**
 * Runs one breakdown. Only the aggregated buckets cross the wire - a 4M-row file and a
 * 4k-row file return the same handful of kilobytes.
 */
export async function fetchStatistics(
  datasetId: string,
  params: StatisticsParams
): Promise<StatisticsOut> {
  const started = performance.now();
  const { data } = await api.post<StatisticsOut>(`/datasets/${datasetId}/statistics`, {
    group_by: params.group_by,
    filters: params.filters ?? [],
    search: params.search ?? null,
    source: params.source ?? "cleaned",
    limit: params.limit ?? 50,
    sort: params.sort ?? "count",
    granularity: params.granularity ?? "year",
    bins: params.bins ?? 20,
  });
  return { ...data, elapsed_ms: Math.round(performance.now() - started) };
}

/** Every column with an estimate of how many distinct values it holds, so the picker
 *  can rank the useful ones and warn about the ones that would make a useless chart. */
export async function fetchColumnSuggestions(
  datasetId: string,
  source: "raw" | "cleaned" = "cleaned"
): Promise<ColumnSuggestion[]> {
  const { data } = await api.get<ColumnSuggestion[]>(
    `/datasets/${datasetId}/statistics/columns`,
    { params: { source } }
  );
  return data;
}

// ---- cross-tab ----

export interface PivotHeader {
  value: string;
  total: number;
  /** blank in the source - shown as its own bucket rather than dropped */
  unspecified: boolean;
  /** everything beyond the requested limit, aggregated exactly */
  other: boolean;
}

export interface PivotRow {
  header: PivotHeader;
  /** one entry per column header, same order */
  cells: number[];
}

export interface PivotOut {
  row_column: string;
  column_column: string;
  row_kind: ColumnKind;
  column_kind: ColumnKind;
  columns: PivotHeader[];
  rows: PivotRow[];
  total: number;
  grand_total: number;
  distinct_rows: number;
  distinct_columns: number;
  rows_truncated: boolean;
  columns_truncated: boolean;
  execution_ms: number;
  elapsed_ms?: number;
}

export interface PivotParams {
  row_column: string;
  column_column: string;
  filters?: FilterRule[];
  search?: string | null;
  source?: "raw" | "cleaned";
  row_limit?: number;
  column_limit?: number;
  row_granularity?: Granularity;
  column_granularity?: Granularity;
}

/** One cross-tab. Only the finished matrix crosses the wire, never the rows behind it. */
export async function fetchPivot(datasetId: string, params: PivotParams): Promise<PivotOut> {
  const started = performance.now();
  const { data } = await api.post<PivotOut>(`/datasets/${datasetId}/pivot`, {
    row_column: params.row_column,
    column_column: params.column_column,
    filters: params.filters ?? [],
    search: params.search ?? null,
    source: params.source ?? "cleaned",
    row_limit: params.row_limit ?? 25,
    column_limit: params.column_limit ?? 12,
    row_granularity: params.row_granularity ?? "year",
    column_granularity: params.column_granularity ?? "year",
  });
  return { ...data, elapsed_ms: Math.round(performance.now() - started) };
}

export interface StatisticsExportRequest {
  format: "csv" | "xlsx" | "pdf";
  title: string;
  subtitle: string;
  headers: string[];
  rows: { label: string; count: number; percentage: number }[];
  total_label: string;
  total: number;
}

/**
 * Downloads the breakdown currently on screen.
 *
 * The rows travel to the server already labelled, so the file says what the screen says
 * - same language, same hidden categories, same order - and the server's only job is to
 * turn them into CSV, XLSX or PDF.
 */
export async function exportStatistics(
  datasetId: string,
  req: StatisticsExportRequest
): Promise<void> {
  const { data } = await api.post<Blob>(`/datasets/${datasetId}/statistics/export`, req, {
    responseType: "blob",
  });

  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${req.title || "statistics"}.${req.format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
