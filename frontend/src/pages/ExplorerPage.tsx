import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import {
  apiErrorMessage,
  applyCleaning,
  downloadExportUrl,
  fetchColumns,
  fetchData,
  fetchGroups,
  getDataset,
  getJob,
  getStats,
  requestExport,
  type ColumnKind,
  type ExportRequest,
  type FilterRule,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ColumnHeaderMenu from "../components/ColumnHeaderMenu";
import ColumnManager from "../components/ColumnManager";
import { columnLabel, usesRawHeaders } from "../data/columnDictionary";
import { hasHebrew, translateValue } from "../data/valueDictionary";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import FilterDialog from "../components/FilterDialog";
import GridCell from "../components/GridCell";
import GroupDialog from "../components/GroupDialog";
import GroupedGrid from "../components/GroupedGrid";
import LoadingState from "../components/LoadingState";
import Pager from "../components/Pager";
import SearchScope from "../components/SearchScope";
import StatsPanel from "../components/StatsPanel";
import {
  IconCheck,
  IconClock,
  IconClose,
  IconColumns,
  IconDownload,
  IconFilter,
  IconRecords,
  IconReset,
  IconSort,
  IconStats,
} from "../components/SheetIcons";

/** Which toolbar panel is expanded under the toolbar strip, if any.
 *  Filtering is a modal dialog rather than a strip panel, so it isn't listed here. */
type Panel = "columns" | "stats" | null;

/** Sub-second timings read better in milliseconds; anything longer in seconds. */
function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}

/** Buckets the elapsed time so the indicator's colour tells the user whether the
 *  operation was cheap or expensive, rather than just being decorative. */
function timingClass(ms: number): "fast" | "medium" | "slow" {
  if (ms < 500) return "fast";
  if (ms < 2000) return "medium";
  return "slow";
}

export default function ExplorerPage() {
  const { t, i18n } = useTranslation();
  const labelFor = (c: string) => columnLabel(c, i18n.language);
  const { datasetId = "" } = useParams();
  const { can } = useAuth();
  const canExport = can("datasets.export");
  const canDeleteColumn = can("datasets.clean");
  const qc = useQueryClient();

  const [source, setSource] = useState<"raw" | "cleaned">("cleaned");
  const [search, setSearch] = useState("");
  // Which columns the search looks in; empty means all of them. Remembered per dataset
  // because it is a statement about this file's columns, and re-narrowing it on every
  // visit would be the kind of chore that stops people using it at all.
  const [searchColumns, setSearchColumns] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(`search-columns:${datasetId}`);
      return raw ? (JSON.parse(raw) as string[]) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(`search-columns:${datasetId}`, JSON.stringify(searchColumns));
    } catch {
      // a browser refusing storage is not a reason to stop working
    }
  }, [datasetId, searchColumns]);
  const [filters, setFilters] = useState<FilterRule[]>([]);
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [exportFormat, setExportFormat] = useState<ExportRequest["format"]>("csv");
  const [exportScope, setExportScope] = useState<ExportRequest["scope"]>("all");
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [showExportReady, setShowExportReady] = useState(false);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});
  const [columnOrder, setColumnOrder] = useState<string[] | null>(null);
  const [dragColumn, setDragColumn] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [translatedColumns, setTranslatedColumns] = useState<Set<string>>(new Set());
  const [panel, setPanel] = useState<Panel>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [groupBy, setGroupBy] = useState<string[]>([]);
  const [groupOpen, setGroupOpen] = useState(false);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [showRowNumbers, setShowRowNumbers] = useState(true);
  const columnsBtnRef = useRef<HTMLButtonElement>(null);
  const isGrouped = groupBy.length > 0;

  const { data: dataset } = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => getDataset(datasetId),
  });

  const { data: stats } = useQuery({
    queryKey: ["stats", datasetId],
    queryFn: () => getStats(datasetId),
  });

  // Column kinds drive the T/# header icons. They only change when the data is
  // reshaped, so they're fetched once per dataset+source rather than per page.
  const { data: columnInfos } = useQuery({
    queryKey: ["columns", datasetId, source],
    queryFn: () => fetchColumns(datasetId, source),
    staleTime: 5 * 60 * 1000,
  });

  // top level of the group tree; the pager drives its paging just like rows
  const { data: groupPage, isFetching: groupsFetching } = useQuery({
    queryKey: ["group", datasetId, source, groupBy[0], filters, search, searchColumns, page, pageSize],
    queryFn: () =>
      fetchGroups(datasetId, {
        column: groupBy[0],
        page,
        page_size: pageSize,
        filters,
        search: search || null,
        search_columns: searchColumns,
        source,
      }),
    enabled: isGrouped,
    placeholderData: (prev) => prev,
  });

  const {
    data: page_,
    isFetching,
    error: dataError,
  } = useQuery({
    queryKey: ["data", datasetId, source, search, searchColumns, filters, sortBy, sortDir, page, pageSize],
    queryFn: () =>
      fetchData(datasetId, {
        page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_dir: sortDir,
        search: search || null,
        search_columns: searchColumns,
        filters,
        source,
      }),
    placeholderData: (prev) => prev,
  });

  const [exportError, setExportError] = useState<string | null>(null);

  const exportMutation = useMutation({
    mutationFn: () =>
      requestExport(datasetId, {
        format: exportFormat,
        scope: exportScope,
        source,
        search: exportScope === "current_view" ? search || null : null,
        search_columns: exportScope === "current_view" ? searchColumns : undefined,
        filters: exportScope === "current_view" ? filters : [],
        sort_by: exportScope === "current_view" ? sortBy : null,
        sort_dir: sortDir,
      }),
    onSuccess: (job) => {
      setExportJobId(job.id);
      setExportError(null);
    },
    onError: (err) => setExportError(apiErrorMessage(err, t("common.error_generic"))),
  });

  const { data: exportJob } = useQuery({
    queryKey: ["job", exportJobId],
    queryFn: () => getJob(exportJobId!),
    enabled: !!exportJobId,
    refetchInterval: (q) => (q.state.data?.status === "done" || q.state.data?.status === "error" ? false : 1000),
    refetchIntervalInBackground: true,
  });

  // Large exports complete in the background. Make the ready file immediately obvious
  // instead of relying on people to notice the toolbar button changed state.
  useEffect(() => {
    if (exportJob?.status === "done") setShowExportReady(true);
  }, [exportJob?.status]);

  const [deleteColumnError, setDeleteColumnError] = useState<string | null>(null);

  /** Keeps exactly the given columns, dropping the rest. Used by "delete hidden". */
  const deleteColumnsMutation = useMutation({
    mutationFn: (keepColumns: string[]) =>
      applyCleaning(datasetId, { keep_columns: keepColumns, dedupe: false, filters: [] }),
    onSuccess: (_res, keepColumns) => {
      const kept = new Set(keepColumns);
      setFilters((prev) => prev.filter((f) => kept.has(f.column)));
      setGroupBy((prev) => prev.filter((c) => kept.has(c)));
      if (sortBy && !kept.has(sortBy)) setSortBy(null);
      setHiddenColumns(new Set());
      setDeleteColumnError(null);
      setColumnsOpen(false);
      qc.invalidateQueries({ queryKey: ["data", datasetId] });
      qc.invalidateQueries({ queryKey: ["group", datasetId] });
      qc.invalidateQueries({ queryKey: ["stats", datasetId] });
      qc.invalidateQueries({ queryKey: ["dataset", datasetId] });
      qc.invalidateQueries({ queryKey: ["columns", datasetId] });
    },
    onError: (err) => setDeleteColumnError(apiErrorMessage(err, t("common.error_generic"))),
  });

  const deleteColumnMutation = useMutation({
    mutationFn: (column: string) => {
      const keepColumns = (page_?.columns ?? []).filter((c) => c !== column);
      return applyCleaning(datasetId, { keep_columns: keepColumns, dedupe: false, filters: [] });
    },
    onSuccess: (_res, column) => {
      setFilters((prev) => prev.filter((f) => f.column !== column));
      if (sortBy === column) setSortBy(null);
      setHiddenColumns((prev) => {
        const next = new Set(prev);
        next.delete(column);
        return next;
      });
      setDeleteColumnError(null);
      qc.invalidateQueries({ queryKey: ["data", datasetId] });
      qc.invalidateQueries({ queryKey: ["stats", datasetId] });
      qc.invalidateQueries({ queryKey: ["dataset", datasetId] });
      qc.invalidateQueries({ queryKey: ["columns", datasetId] });
    },
    onError: (err) => setDeleteColumnError(apiErrorMessage(err, t("common.error_generic"))),
  });

  // a finished export is tied to the format/scope it was generated with, so drop it
  // whenever either changes - otherwise the Download button would hand back a stale file.
  function resetExport() {
    setExportJobId(null);
    setExportError(null);
    setShowExportReady(false);
  }

  function handleSort(col: string, dir: "asc" | "desc") {
    setSortBy(col);
    setSortDir(dir);
    setPage(1);
  }

  function toggleTranslateColumn(col: string) {
    setTranslatedColumns((prev) => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col);
      else next.add(col);
      return next;
    });
  }

  function toggleHideColumn(col: string) {
    setHiddenColumns((prev) => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col);
      else next.add(col);
      return next;
    });
  }

  /** Permanently drops every hidden column - the natural follow-up to hiding a batch of
   *  columns you never want to see again. Rebuilds the cleaned table, so it is confirmed. */
  function handleDeleteHiddenColumns() {
    const doomed = allColumns.filter((c) => hiddenColumns.has(c));
    if (doomed.length === 0) return;
    const message = t("sheet.confirm_delete_hidden", {
      count: doomed.length,
      columns: doomed.map(labelFor).join("، "),
    });
    if (!window.confirm(message ?? "")) return;
    deleteColumnsMutation.mutate(allColumns.filter((c) => !hiddenColumns.has(c)));
  }

  function handleDeleteColumn(col: string) {
    const message = t("column_menu.confirm_delete", { column: labelFor(col) });
    if (window.confirm(message ?? "")) deleteColumnMutation.mutate(col);
  }

  const MIN_COLUMN_WIDTH = 90;

  /** Drag the divider at a header's trailing edge to resize that column. The pointer
   *  delta is inverted under RTL, where dragging outward means moving left. */
  function startResize(e: React.MouseEvent, column: string) {
    e.preventDefault();
    e.stopPropagation();
    const th = (e.currentTarget as HTMLElement).closest("th");
    if (!th) return;
    const rtl = document.documentElement.dir === "rtl";
    const startX = e.clientX;
    const startWidth = th.getBoundingClientRect().width;

    function onMove(ev: MouseEvent) {
      const delta = rtl ? startX - ev.clientX : ev.clientX - startX;
      const next = Math.max(MIN_COLUMN_WIDTH, Math.round(startWidth + delta));
      setColumnWidths((prev) => ({ ...prev, [column]: next }));
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.classList.remove("is-resizing-column");
    }
    document.body.classList.add("is-resizing-column");
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  /** Drops the dragged column into the target's slot, keeping every other column's
   *  relative order. Works on the full column list (not just the visible ones) so that
   *  hidden columns keep a sensible position when shown again. */
  function moveColumn(from: string, to: string) {
    if (from === to) return;
    setColumnOrder(() => {
      const base = orderedColumns.slice();
      const fromIdx = base.indexOf(from);
      const toIdx = base.indexOf(to);
      if (fromIdx < 0 || toIdx < 0) return base;
      base.splice(fromIdx, 1);
      base.splice(toIdx, 0, from);
      return base;
    });
  }

  /** Double-clicking the divider hands the column back to automatic sizing. */
  function resetWidth(column: string) {
    setColumnWidths((prev) => {
      const next = { ...prev };
      delete next[column];
      return next;
    });
  }

  function resetView() {
    setSearch("");
    setFilters([]);
    setSortBy(null);
    setSortDir("asc");
    setHiddenColumns(new Set());
    setColumnWidths({});
    setColumnOrder(null);
    setTranslatedColumns(new Set());
    setGroupBy([]);
    setPage(1);
    resetExport();
  }

  function togglePanel(next: Panel) {
    setPanel((prev) => (prev === next ? null : next));
  }

  const allColumns = page_?.columns ?? [];
  const kindByColumn = new Map<string, ColumnKind>((columnInfos ?? []).map((c) => [c.name, c.kind]));

  // User order first, then any column it doesn't mention (new or renamed ones), so the
  // saved order survives a column being added or deleted.
  const orderedColumns = columnOrder
    ? [...columnOrder.filter((c) => allColumns.includes(c)), ...allColumns.filter((c) => !columnOrder.includes(c))]
    : allColumns;
  const visibleColumns = orderedColumns.filter((c) => !hiddenColumns.has(c));
  // index of each visible column within the row tuple, which always follows the
  // server's original column order
  const visibleIndexes = visibleColumns.map((c) => allColumns.indexOf(c));

  // Which columns hold Hebrew text, judged from the rows currently on screen. Only those
  // are offered a "translate values" toggle - and never while the UI itself is in Hebrew,
  // where showing the file untouched is the whole point.
  const rawMode = usesRawHeaders(i18n.language);
  const hebrewColumns = new Set<string>();
  if (!rawMode) {
    for (const row of page_?.rows ?? []) {
      allColumns.forEach((c, i) => {
        if (!hebrewColumns.has(c) && hasHebrew(String(row[i] ?? ""))) hebrewColumns.add(c);
      });
    }
  }
  const totalRows = page_?.total_rows ?? 0;
  // rows in the whole source table, so the toolbar can show "matched of total" while a
  // search or filter is narrowing the view
  const sourceTotal =
    (source === "cleaned" ? stats?.row_count_cleaned ?? stats?.row_count_raw : stats?.row_count_raw) ?? 0;
  const isNarrowed = sourceTotal > 0 && totalRows < sourceTotal;
  const rowsOnPage = page_?.rows.length ?? 0;
  const firstRowIndex = (page - 1) * pageSize + 1;
  // when grouping, the pager walks groups rather than rows
  const pagedTotal = isGrouped ? groupPage?.total_groups ?? 0 : totalRows;
  const totalPages = Math.max(1, Math.ceil(pagedTotal / pageSize));
  const activeFilterCount = filters.length;
  const isDirty =
    !!search ||
    filters.length > 0 ||
    !!sortBy ||
    hiddenColumns.size > 0 ||
    isGrouped ||
    Object.keys(columnWidths).length > 0 ||
    columnOrder !== null ||
    page !== 1;

  return (
    <div className="sheet">
      {/* The live region is always here and only its contents change. A region that
          appears at the same moment as its text is not reliably announced - some screen
          readers only watch regions that were already present. It is fixed, empty and
          click-through until there is something to say. */}
      <div className="export-ready-region" role="status" aria-live="polite">
        {showExportReady && exportJob?.status === "done" && (
        <div className="export-ready-toast">
          <span className="export-ready-icon"><IconCheck /></span>
          <a
            className="export-ready-copy"
            href={downloadExportUrl(datasetId, exportJob.id)}
            onClick={() => setShowExportReady(false)}
          >
            <strong>{t("explorer.export_ready_title")}</strong>
            <span>{t("explorer.export_ready_body")}</span>
            <em>{t("explorer.export_ready_action")}</em>
          </a>
          <button
            type="button"
            className="export-ready-close"
            onClick={() => setShowExportReady(false)}
            aria-label={t("explorer.export_ready_close")}
          >
            <IconClose />
          </button>
        </div>
        )}
      </div>
      <div className="sheet-titlebar">
        <Link to="/" className="sheet-back">
          {t("common.back")}
        </Link>
        <span className="sheet-name" title={dataset?.original_filename}>
          {dataset?.original_filename ?? "…"}
        </span>
        <span className="sheet-source">
          <select
            value={source}
            onChange={(e) => {
              setSource(e.target.value as "raw" | "cleaned");
              setPage(1);
            }}
          >
            <option value="cleaned">{t("explorer.source_cleaned")}</option>
            <option value="raw">{t("explorer.source_raw")}</option>
          </select>
        </span>
      </div>

      <div className="sheet-toolbar">
        <button type="button" className="sheet-tool" onClick={resetView} disabled={!isDirty}>
          <IconReset />
          {t("sheet.reset")}
        </button>
        <button
          type="button"
          ref={columnsBtnRef}
          className={`sheet-tool${columnsOpen || hiddenColumns.size > 0 ? " active" : ""}`}
          onClick={() => setColumnsOpen((o) => !o)}
        >
          <IconColumns />
          {t("sheet.manage_columns")}
          {hiddenColumns.size > 0 && <span className="sheet-badge">{hiddenColumns.size}</span>}
        </button>
        <button
          type="button"
          className={`sheet-tool${activeFilterCount > 0 ? " active" : ""}`}
          onClick={() => setFilterOpen(true)}
        >
          <IconFilter />
          {t("sheet.filter")}
          {activeFilterCount > 0 && <span className="sheet-badge">{activeFilterCount}</span>}
        </button>
        <button
          type="button"
          className={`sheet-tool${isGrouped ? " active" : ""}`}
          onClick={() => setGroupOpen(true)}
        >
          <IconColumns />
          {isGrouped ? t("group.grouped_by", { count: groupBy.length }) : t("group.title")}
        </button>
        <button
          type="button"
          className={`sheet-tool${sortBy ? " active" : ""}`}
          onClick={() => sortBy && setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
          disabled={!sortBy}
          title={sortBy ? `${sortBy} · ${sortDir}` : undefined}
        >
          <IconSort />
          {sortBy ? `${labelFor(sortBy)} ${sortDir === "asc" ? "↑" : "↓"}` : t("sheet.sort")}
        </button>
        <button
          type="button"
          className={`sheet-tool${panel === "stats" ? " active" : ""}`}
          onClick={() => togglePanel("stats")}
        >
          <IconStats />
          {t("sheet.stats")}
        </button>

        <span className="sheet-toolbar-sep" />

        <input
          type="search"
          className="sheet-search"
          placeholder={t("explorer.search_placeholder") ?? ""}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />

        <SearchScope
          columns={allColumns}
          selected={searchColumns}
          onChange={(next) => {
            setSearchColumns(next);
            setPage(1);
          }}
        />

        <span className="sheet-toolbar-spacer" />

        <span
          className="sheet-count"
          title={
            isNarrowed
              ? `${totalRows.toLocaleString()} / ${sourceTotal.toLocaleString()}`
              : undefined
          }
        >
          <IconRecords />
          <strong>{totalRows.toLocaleString()}</strong>
          {isNarrowed && (
            <span className="sheet-count-total">
              {t("explorer.of")} {sourceTotal.toLocaleString()}
            </span>
          )}
          {t("sheet.records")}
        </span>

        {page_ &&
          (() => {
            const elapsed = page_.elapsed_ms ?? page_.duration_ms;
            return (
              <span
                className={`sheet-timing ${timingClass(elapsed)}${isFetching ? " busy" : ""}`}
                title={t("sheet.timing_detail", {
                  server: formatMs(page_.duration_ms),
                  total: formatMs(elapsed),
                })}
              >
                <IconClock />
                {isFetching ? "…" : formatMs(elapsed)}
              </span>
            );
          })()}

        {canExport && (
          <>
            <select
              value={exportFormat}
              onChange={(e) => {
                setExportFormat(e.target.value as ExportRequest["format"]);
                resetExport();
              }}
            >
              <option value="csv">CSV</option>
              <option value="xlsx">Excel</option>
              <option value="pdf">PDF</option>
            </select>
            <select
              value={exportScope}
              onChange={(e) => {
                setExportScope(e.target.value as ExportRequest["scope"]);
                resetExport();
              }}
            >
              <option value="all">{t("explorer.export_scope_all")}</option>
              <option value="current_view">{t("explorer.export_scope_view")}</option>
            </select>
            {exportJob?.status === "done" ? (
              <a className="sheet-tool primary" href={downloadExportUrl(datasetId, exportJob.id)}>
                <IconDownload />
                {t("explorer.download")}
              </a>
            ) : (
              <button
                type="button"
                className="sheet-tool primary"
                onClick={() => exportMutation.mutate()}
                disabled={exportMutation.isPending || (!!exportJob && exportJob.status !== "error")}
              >
                <IconDownload />
                {exportJob && exportJob.status !== "error" ? t("explorer.exporting") : t("explorer.export")}
              </button>
            )}
          </>
        )}
      </div>

      {isGrouped && (
        <div className="group-chips">
          {groupBy.map((c) => (
            <span className="group-chip" key={c} title={c}>
              {labelFor(c)}
              <button
                type="button"
                // functional update: two chips removed in the same tick would otherwise
                // both read the pre-update array and one removal would be lost
                onClick={() => setGroupBy((prev) => prev.filter((g) => g !== c))}
                aria-label={t("cleaning.remove")}
              >
                <IconClose />
              </button>
            </span>
          ))}
        </div>
      )}

      <GroupDialog
        open={groupOpen}
        columns={allColumns}
        groupBy={groupBy}
        kindByColumn={kindByColumn}
        onApply={(next) => {
          setGroupBy(next);
          setPage(1);
        }}
        onClose={() => setGroupOpen(false)}
      />

      <FilterDialog
        open={filterOpen}
        columns={allColumns}
        filters={filters}
        datasetId={datasetId}
        source={source}
        kindByColumn={kindByColumn}
        onApply={(next) => {
          setFilters(next);
          setPage(1);
        }}
        onClose={() => setFilterOpen(false)}
      />

      <ColumnManager
        open={columnsOpen}
        onClose={() => setColumnsOpen(false)}
        anchorRef={columnsBtnRef}
        columns={allColumns}
        hidden={hiddenColumns}
        kindByColumn={kindByColumn}
        onToggle={toggleHideColumn}
        onSetHidden={setHiddenColumns}
        showRowNumbers={showRowNumbers}
        onToggleRowNumbers={() => setShowRowNumbers((v) => !v)}
        canDelete={canDeleteColumn}
        onDeleteHidden={handleDeleteHiddenColumns}
      />

      {panel === "stats" && stats && (
        <div className="sheet-panel">
          <StatsPanel stats={stats} />
        </div>
      )}

      <ErrorBanner message={deleteColumnError} />
      <ErrorBanner message={exportError} />
      {exportJob?.status === "error" && <ErrorBanner message={exportJob.error_message} />}

      <div className="sheet-grid">
        {isGrouped ? (
          !groupPage || groupPage.groups.length === 0 ? (
            groupsFetching ? (
              <LoadingState />
            ) : (
              <EmptyState message={t("explorer.no_data")} />
            )
          ) : (
            <GroupedGrid
              datasetId={datasetId}
              source={source}
              groupBy={groupBy}
              filters={filters}
              search={search || null}
              visibleColumns={visibleColumns}
              visibleIndexes={visibleIndexes}
              allColumns={allColumns}
              kindByColumn={kindByColumn}
              labelFor={labelFor}
              topGroups={groupPage.groups}
              translatedColumns={translatedColumns}
            />
          )
        ) : !page_ || page_.rows.length === 0 ? (
          isFetching ? (
            <LoadingState />
          ) : dataError ? (
            <ErrorBanner message={apiErrorMessage(dataError, t("common.error_loading_data"))} />
          ) : (
            <EmptyState message={t("explorer.no_data")} />
          )
        ) : (
          <table>
            <thead>
              <tr>
                {showRowNumbers && <th className="rownum-col">#</th>}
                {visibleColumns.map((c) => {
                  const w = columnWidths[c];
                  const classes = [
                    sortBy === c ? "is-sorted" : "",
                    filters.some((f) => f.column === c) ? "is-filtered" : "",
                    dragColumn === c ? "is-dragging" : "",
                    dropTarget === c && dragColumn !== c ? "is-drop-target" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <th
                      key={c}
                      className={classes || undefined}
                      style={w ? { width: w, minWidth: w, maxWidth: w } : undefined}
                      draggable
                      onDragStart={(e) => {
                        // dragging must not start from the resize handle
                        if ((e.target as HTMLElement).classList.contains("col-resizer")) {
                          e.preventDefault();
                          return;
                        }
                        setDragColumn(c);
                        e.dataTransfer.effectAllowed = "move";
                        e.dataTransfer.setData("text/plain", c);
                      }}
                      onDragOver={(e) => {
                        if (!dragColumn) return;
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                        if (dropTarget !== c) setDropTarget(c);
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        if (dragColumn) moveColumn(dragColumn, c);
                        setDragColumn(null);
                        setDropTarget(null);
                      }}
                      onDragEnd={() => {
                        setDragColumn(null);
                        setDropTarget(null);
                      }}
                    >
                      <ColumnHeaderMenu
                        column={c}
                        kind={kindByColumn.get(c)}
                        datasetId={datasetId}
                        source={source}
                        sortBy={sortBy}
                        sortDir={sortDir}
                        onSort={handleSort}
                        filters={filters}
                        onFiltersChange={(f) => {
                          setFilters(f);
                          setPage(1);
                        }}
                        onHide={() => toggleHideColumn(c)}
                        canDelete={canDeleteColumn}
                        onDeleteColumn={() => handleDeleteColumn(c)}
                        canTranslate={hebrewColumns.has(c)}
                        translated={translatedColumns.has(c)}
                        onToggleTranslate={() => toggleTranslateColumn(c)}
                      />
                      <span
                        className="col-resizer"
                        role="separator"
                        aria-label={t("sheet.resize_column")}
                        onMouseDown={(e) => startResize(e, c)}
                        onDoubleClick={() => resetWidth(c)}
                      />
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {page_.rows.map((row, i) => (
                <tr key={i}>
                  {showRowNumbers && (
                    <td className="rownum-col">{(firstRowIndex + i).toLocaleString()}</td>
                  )}
                  {visibleIndexes.map((colIdx) => {
                    const col = allColumns[colIdx];
                    const kind = kindByColumn.get(col);
                    const raw = String(row[colIdx] ?? "");
                    const shown = translatedColumns.has(col)
                      ? translateValue(raw, i18n.language)
                      : raw;
                    return (
                      // the tooltip keeps the stored value reachable when translated
                      <td key={colIdx} className={`cell-${kind ?? "text"}`} title={raw}>
                        <GridCell value={shown} kind={kind} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="sheet-statusbar">
        <span className="sheet-status-group">
          {t("sheet.view")}
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(1);
            }}
          >
            {[25, 50, 100, 200, 500].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </span>

        <Pager
          page={page}
          totalPages={totalPages}
          onChange={setPage}
          labels={{
            first: t("sheet.first_page"),
            prev: t("explorer.prev"),
            next: t("explorer.next"),
            last: t("sheet.last_page"),
            goTo: t("sheet.go_to_page"),
          }}
        />

        <span className="sheet-status-group muted sheet-status-range">
          {isGrouped
            ? t("group.groups_count", { count: groupPage?.total_groups ?? 0 })
            : totalRows > 0 &&
              t("sheet.showing_range", {
                from: firstRowIndex.toLocaleString(),
                to: Math.min(firstRowIndex + rowsOnPage - 1, totalRows).toLocaleString(),
                total: totalRows.toLocaleString(),
              })}
          {" · "}
          {t("sheet.cols")}: {visibleColumns.length} {t("explorer.of")} {allColumns.length}
          {isFetching && ` · ${t("common.loading")}`}
        </span>
      </div>
    </div>
  );
}

