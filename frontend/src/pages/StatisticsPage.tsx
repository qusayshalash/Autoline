import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import type { FilterRule } from "../api/client";
import type { Granularity } from "../api/statistics";
import {
  exportStatistics,
  fetchColumnSuggestions,
  fetchPivot,
  fetchStatistics,
} from "../api/statistics";
import type { AnalysisMode } from "../components/stats/AnalysisSetup";
import AnalysisSetup from "../components/stats/AnalysisSetup";
import type { PivotMeasure } from "../components/stats/PivotTable";
import PivotTable from "../components/stats/PivotTable";
import BrandCard from "../components/stats/BrandCard";
import BreakdownCharts from "../components/stats/BreakdownCharts";
import BreakdownTable from "../components/stats/BreakdownTable";
import InsightNotes from "../components/stats/InsightNotes";
import KpiCards from "../components/stats/KpiCards";
import { IconClock, IconDownload } from "../components/stats/StatsIcons";
import { formatCount, formatDuration } from "../components/stats/labels";
import { buildRows } from "../components/stats/rows";
import { brandFor } from "../data/brandRegistry";
import { columnLabel } from "../data/columnDictionary";
import { usesRawHeaders } from "../data/columnDictionary";

/** Where the dashboard starts, in order of preference. Fuel type is the breakdown this
 *  screen was built around, so it leads when the file has it. */
const PREFERRED_COLUMNS = ["sug_delek_nm", "baalut", "tozeret_nm", "shnat_yitzur"];

/** Columns wide enough to make a chart nobody can read are never chosen automatically. */
const AUTO_MAX_DISTINCT = 200;

export default function StatisticsPage() {
  const { datasetId = "" } = useParams();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const [groupBy, setGroupBy] = useState("");
  const [filters, setFilters] = useState<FilterRule[]>([]);
  const [granularity, setGranularity] = useState<Granularity>("year");
  const [showPercent, setShowPercent] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState(false);
  const [mode, setMode] = useState<AnalysisMode>("breakdown");
  const [pivotColumn, setPivotColumn] = useState("");
  const [measure, setMeasure] = useState<PivotMeasure>("count");

  // Hebrew is the language these files are written in, so their values are already
  // readable and translating them would be the odd choice; in Arabic and English the
  // dictionary earns its keep.
  const [translate, setTranslate] = useState(() => !usesRawHeaders(i18n.language));
  useEffect(() => setTranslate(!usesRawHeaders(lang)), [lang]);

  const { data: columns = [], isLoading: loadingColumns } = useQuery({
    queryKey: ["stats-columns", datasetId],
    queryFn: () => fetchColumnSuggestions(datasetId),
    enabled: !!datasetId,
  });

  // Reset to a sensible breakdown whenever the file changes, and never leave groupBy
  // pointing at a column the new file doesn't have.
  useEffect(() => {
    if (columns.length === 0) return;
    setGroupBy((current) => {
      if (current && columns.some((c) => c.name === current)) return current;
      const preferred = PREFERRED_COLUMNS.find((name) =>
        columns.some((c) => c.name === name)
      );
      if (preferred) return preferred;
      const usable = columns
        .filter((c) => c.approx_distinct > 1 && c.approx_distinct <= AUTO_MAX_DISTINCT)
        .sort((a, b) => a.approx_distinct - b.approx_distinct);
      return usable[0]?.name ?? columns[0].name;
    });
  }, [columns]);

  useEffect(() => {
    setFilters([]);
    setHidden(new Set());
  }, [datasetId]);

  // The second axis defaults to whatever the first is not: the pairing that answers a
  // question is almost always "the thing I am measuring" against "the thing I am
  // comparing across", so a maker/fuel pair is a better opening than two arbitrary
  // columns.
  useEffect(() => {
    if (columns.length === 0 || !groupBy) return;
    setPivotColumn((current) => {
      if (current && current !== groupBy && columns.some((c) => c.name === current)) return current;
      const preferred = PREFERRED_COLUMNS.find(
        (name) => name !== groupBy && columns.some((c) => c.name === name)
      );
      if (preferred) return preferred;
      const usable = columns
        .filter((c) => c.name !== groupBy && c.approx_distinct > 1 && c.approx_distinct <= AUTO_MAX_DISTINCT)
        .sort((a, b) => a.approx_distinct - b.approx_distinct);
      return usable[0]?.name ?? "";
    });
  }, [columns, groupBy]);

  const {
    data: stats,
    isFetching,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["statistics", datasetId, groupBy, filters, granularity],
    queryFn: () =>
      fetchStatistics(datasetId, {
        group_by: groupBy,
        filters,
        granularity,
        sort: granularity && isDateColumn(columns, groupBy) ? "value" : "count",
        limit: 50,
      }),
    enabled: !!datasetId && !!groupBy && mode === "breakdown",
    placeholderData: (prev) => prev,
  });

  const { data: pivot, isFetching: pivotFetching } = useQuery({
    queryKey: ["pivot", datasetId, groupBy, pivotColumn, filters, granularity],
    queryFn: () =>
      fetchPivot(datasetId, {
        row_column: groupBy,
        column_column: pivotColumn,
        filters,
        row_granularity: granularity,
        row_limit: 25,
        column_limit: 12,
      }),
    enabled: !!datasetId && !!groupBy && !!pivotColumn && mode === "pivot",
    placeholderData: (prev) => prev,
  });

  // Hiding a category is about the breakdown on screen; a new breakdown starts fresh.
  useEffect(() => setHidden(new Set()), [groupBy, granularity]);

  const rows = useMemo(
    () => (stats ? buildRows(stats, t, lang, translate, hidden) : []),
    [stats, t, lang, translate, hidden]
  );

  /** The manufacturer the filters pin down, if they pin exactly one down. */
  const brandSubject = useMemo(() => {
    const rule = filters.find(
      (f) =>
        (f.column === "tozeret_nm" || f.column === "kinuy_mishari") &&
        (f.op === "eq" || f.op === "starts_with" || f.op === "contains") &&
        String(f.value ?? "").trim()
    );
    if (!rule) return null;
    const raw = String(rule.value);
    return { raw, brand: brandFor(raw) };
  }, [filters]);

  function toggle(key: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function runExport(format: "csv" | "xlsx" | "pdf") {
    if (!stats) return;
    setExporting(true);
    try {
      const visible = rows.filter((r) => !r.hidden);
      await exportStatistics(datasetId, {
        format,
        title: t("statistics.export_title", { column: columnLabel(groupBy, lang) }),
        subtitle: [
          t("statistics.export_scope", { total: formatCount(stats.total, lang) }),
          filters
            .map((f) => `${columnLabel(f.column, lang)} ${t(`cleaning.op_${f.op}`)} ${f.value ?? ""}`)
            .join(" · "),
        ]
          .filter(Boolean)
          .join(" — "),
        headers: [t("statistics.value"), t("statistics.count"), t("statistics.share")],
        rows: visible.map((r) => ({
          label: r.label,
          count: r.count,
          percentage: r.percentage,
        })),
        total_label: t("statistics.total"),
        total: visible.reduce((a, r) => a + r.count, 0),
      });
    } finally {
      setExporting(false);
    }
  }

  if (!datasetId) return <p className="muted">{t("statistics.pick_file")}</p>;
  if (loadingColumns) return <p className="muted">{t("common.loading")}</p>;
  if (columns.length === 0) return <p className="muted">{t("statistics.no_columns")}</p>;

  return (
    <div className="stats-page">
      <AnalysisSetup
        datasetId={datasetId}
        source="cleaned"
        columns={columns}
        mode={mode}
        onMode={setMode}
        pivotColumn={pivotColumn}
        onPivotColumn={setPivotColumn}
        onSwapAxes={() => {
          const a = groupBy;
          setGroupBy(pivotColumn);
          setPivotColumn(a);
        }}
        groupBy={groupBy}
        onGroupBy={setGroupBy}
        filters={filters}
        onFilters={setFilters}
        granularity={granularity}
        onGranularity={setGranularity}
        translate={translate}
        onReset={() => {
          setFilters([]);
          setHidden(new Set());
        }}
        isFetching={mode === "pivot" ? pivotFetching : isFetching}
      />

      {error && <p className="stats-error">{t("common.error_loading_data")}</p>}

      {mode === "pivot" && !pivot && pivotFetching && (
        <div className="stats-loading">
          <span className="stats-spinner" />
          <p>{t("statistics.computing")}</p>
        </div>
      )}

      {mode === "pivot" && pivot && (
        <>
          <div className="stats-actionbar">
            <div className="stats-timing" title={t("statistics.timing_detail") ?? ""}>
              <IconClock />
              <span>
                {t("statistics.computed_in", {
                  server: formatDuration(pivot.execution_ms, lang),
                  total: formatDuration(pivot.elapsed_ms ?? pivot.execution_ms, lang),
                })}
              </span>
            </div>

            <div className="stats-toggle" role="group" aria-label={t("pivot.measure") ?? ""}>
              {(["count", "row", "column", "total"] as PivotMeasure[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  className={measure === m ? "active" : ""}
                  onClick={() => setMeasure(m)}
                >
                  {t(`pivot.measure_${m}`)}
                </button>
              ))}
            </div>

            <label className="stats-switch">
              <input
                type="checkbox"
                checked={translate}
                onChange={(e) => setTranslate(e.target.checked)}
              />
              <span>{t("statistics.translate_values")}</span>
            </label>
          </div>

          {pivot.total === 0 ? (
            <div className="stats-empty">
              <h3>{t("statistics.no_results")}</h3>
              <p>{t("statistics.no_results_hint")}</p>
            </div>
          ) : (
            <PivotTable pivot={pivot} measure={measure} translate={translate} />
          )}
        </>
      )}

      {mode === "breakdown" && isLoading && !stats && (
        <div className="stats-loading">
          <span className="stats-spinner" />
          <p>{t("statistics.computing")}</p>
        </div>
      )}

      {mode === "breakdown" && stats && (
        <>
          <div className="stats-actionbar">
            <div className="stats-timing" title={t("statistics.timing_detail") ?? ""}>
              <IconClock />
              <span>
                {t("statistics.computed_in", {
                  server: formatDuration(stats.execution_ms, lang),
                  total: formatDuration(stats.elapsed_ms ?? stats.execution_ms, lang),
                })}
              </span>
            </div>

            <div className="stats-toggle" role="group" aria-label={t("statistics.display") ?? ""}>
              <button
                type="button"
                className={showPercent ? "" : "active"}
                onClick={() => setShowPercent(false)}
              >
                {t("statistics.counts")}
              </button>
              <button
                type="button"
                className={showPercent ? "active" : ""}
                onClick={() => setShowPercent(true)}
              >
                {t("statistics.percentages")}
              </button>
            </div>

            <label className="stats-switch">
              <input
                type="checkbox"
                checked={translate}
                onChange={(e) => setTranslate(e.target.checked)}
              />
              <span>{t("statistics.translate_values")}</span>
            </label>

            <div className="stats-export">
              <IconDownload />
              <span>{t("statistics.export")}</span>
              <button type="button" disabled={exporting} onClick={() => runExport("csv")}>
                CSV
              </button>
              <button type="button" disabled={exporting} onClick={() => runExport("xlsx")}>
                Excel
              </button>
              <button type="button" disabled={exporting} onClick={() => runExport("pdf")}>
                PDF
              </button>
            </div>
          </div>

          {/* A brand card over zero rows would announce a manufacturer that isn't in the
              results at all; the empty state below says the useful thing instead. */}
          {brandSubject && stats.total > 0 && (
            <BrandCard
              brand={brandSubject.brand}
              rawValue={brandSubject.raw}
              matched={stats.total}
              grandTotal={stats.grand_total}
            />
          )}

          {stats.total === 0 ? (
            <div className="stats-empty">
              <h3>{t("statistics.no_results")}</h3>
              <p>{t("statistics.no_results_hint")}</p>
            </div>
          ) : (
            <>
              <KpiCards stats={stats} rows={rows} onToggle={toggle} />
              <BreakdownCharts
                stats={stats}
                rows={rows}
                showPercent={showPercent}
                onToggle={toggle}
                onShowAll={() => setHidden(new Set())}
              />
              <InsightNotes
                stats={stats}
                rows={rows}
                subject={
                  brandSubject
                    ? t("statistics.subject_brand", {
                        brand: brandSubject.brand
                          ? lang.startsWith("ar")
                            ? brandSubject.brand.ar
                            : brandSubject.brand.en
                          : brandSubject.raw,
                      })
                    : undefined
                }
              />
              <BreakdownTable rows={rows} total={stats.total} onToggle={toggle} />
            </>
          )}
        </>
      )}
    </div>
  );
}

function isDateColumn(
  columns: { name: string; kind: string }[],
  name: string
): boolean {
  return columns.find((c) => c.name === name)?.kind === "date";
}
