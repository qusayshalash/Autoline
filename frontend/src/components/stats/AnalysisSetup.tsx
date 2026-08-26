import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { FilterOp, FilterRule } from "../../api/client";
import type { ColumnSuggestion, Granularity } from "../../api/statistics";
import { columnLabel } from "../../data/columnDictionary";
import { translateValue } from "../../data/valueDictionary";
import ValueAutocomplete from "../ValueAutocomplete";
import { IconClose, IconFilter, IconPlus, IconReset } from "./StatsIcons";

/** Above this many distinct values a column makes a chart nobody can read, so the picker
 *  says so rather than letting the user discover it by trying. */
const UNSUITABLE_DISTINCT = 5000;

/** Operators offered per column kind. A date or a number gets ranges; text gets matching.
 *  `in` is left out on purpose - it needs a multi-select, and the chips read better with
 *  one value per rule anyway.
 *
 *  `starts_with` sits right after `contains` because on this data it is usually the one
 *  you want: the manufacturer column reads "maker + country", and several countries end
 *  in the same letters as a maker ("קיה" is the tail of both "טורקיה" and "סלובקיה"), so
 *  `contains` on a marque quietly picks up other marques assembled there. */
const OPS_BY_KIND: Record<string, FilterOp[]> = {
  text: ["eq", "neq", "starts_with", "contains", "ends_with", "is_null", "not_null"],
  category: ["eq", "neq", "is_null", "not_null"],
  number: ["eq", "neq", "gte", "lte", "gt", "lt", "is_null", "not_null"],
  date: ["eq", "gte", "lte", "is_null", "not_null"],
};

const VALUELESS_OPS = new Set<FilterOp>(["is_null", "not_null"]);

export type AnalysisMode = "breakdown" | "pivot";

interface Props {
  datasetId: string;
  source: "raw" | "cleaned";
  columns: ColumnSuggestion[];
  mode: AnalysisMode;
  onMode: (mode: AnalysisMode) => void;
  /** the second axis, used only in cross-tab mode */
  pivotColumn: string;
  onPivotColumn: (column: string) => void;
  onSwapAxes: () => void;
  groupBy: string;
  onGroupBy: (column: string) => void;
  filters: FilterRule[];
  onFilters: (filters: FilterRule[]) => void;
  granularity: Granularity;
  onGranularity: (g: Granularity) => void;
  translate: boolean;
  onReset: () => void;
  isFetching: boolean;
}

export default function AnalysisSetup({
  datasetId,
  source,
  columns,
  mode,
  onMode,
  pivotColumn,
  onPivotColumn,
  onSwapAxes,
  groupBy,
  onGroupBy,
  filters,
  onFilters,
  granularity,
  onGranularity,
  translate,
  onReset,
  isFetching,
}: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const kinds = useMemo(
    () => Object.fromEntries(columns.map((c) => [c.name, c.kind])),
    [columns]
  );
  const groupColumn = columns.find((c) => c.name === groupBy);

  const [draft, setDraft] = useState<FilterRule | null>(null);

  // a draft aimed at a column that no longer exists (file switched) would silently
  // produce an invalid rule, so it is dropped rather than carried across
  useEffect(() => {
    if (draft && !columns.some((c) => c.name === draft.column)) setDraft(null);
  }, [columns, draft]);

  function startDraft() {
    // Open on a column somebody would actually filter by. The first column in the file
    // is usually an identifier, which every row has a different value of - a filter on
    // it matches one row and teaches the user nothing.
    const usable = columns
      .filter((c) => c.name !== groupBy && c.approx_distinct > 1)
      .sort((a, b) => a.approx_distinct - b.approx_distinct);
    const first = usable[0] ?? columns.find((c) => c.name !== groupBy) ?? columns[0];
    if (!first) return;
    setDraft({ column: first.name, op: defaultOp(kinds[first.name]), value: "" });
  }

  function commitDraft() {
    if (!draft) return;
    if (!VALUELESS_OPS.has(draft.op) && !String(draft.value ?? "").trim()) return;
    onFilters([...filters, draft]);
    setDraft(null);
  }

  return (
    <section className="stats-setup">
      <header className="stats-setup-head">
        <h2>
          <IconFilter />
          {t("statistics.setup")}
        </h2>
        <div className="stats-mode" role="group" aria-label={t("pivot.mode") ?? ""}>
          <button
            type="button"
            className={mode === "breakdown" ? "active" : ""}
            onClick={() => onMode("breakdown")}
          >
            {t("pivot.mode_breakdown")}
          </button>
          <button
            type="button"
            className={mode === "pivot" ? "active" : ""}
            onClick={() => onMode("pivot")}
          >
            {t("pivot.mode_pivot")}
          </button>
        </div>
        <button
          type="button"
          className="stats-reset"
          onClick={onReset}
          disabled={filters.length === 0 && !draft}
        >
          <IconReset />
          {t("statistics.reset_analysis")}
        </button>
      </header>

      <div className="stats-setup-row">
        <label className="stats-field">
          <span>{mode === "pivot" ? t("pivot.rows_axis") : t("statistics.analyse_by")}</span>
          <select value={groupBy} onChange={(e) => onGroupBy(e.target.value)}>
            {columns.map((c) => (
              <option key={c.name} value={c.name} disabled={c.approx_distinct >= UNSUITABLE_DISTINCT}>
                {columnLabel(c.name, lang)}
                {c.approx_distinct >= UNSUITABLE_DISTINCT
                  ? ` — ${t("statistics.too_many_values")}`
                  : ""}
              </option>
            ))}
          </select>
        </label>

        {mode === "pivot" && (
          <>
            <button
              type="button"
              className="stats-swap"
              onClick={onSwapAxes}
              title={t("pivot.swap") ?? ""}
              aria-label={t("pivot.swap") ?? ""}
            >
              ⇄
            </button>
            <label className="stats-field">
              <span>{t("pivot.columns_axis")}</span>
              <select value={pivotColumn} onChange={(e) => onPivotColumn(e.target.value)}>
                {columns
                  .filter((c) => c.name !== groupBy)
                  .map((c) => (
                    <option
                      key={c.name}
                      value={c.name}
                      disabled={c.approx_distinct >= UNSUITABLE_DISTINCT}
                    >
                      {columnLabel(c.name, lang)}
                      {c.approx_distinct >= UNSUITABLE_DISTINCT
                        ? ` — ${t("statistics.too_many_values")}`
                        : ""}
                    </option>
                  ))}
              </select>
            </label>
          </>
        )}

        {mode === "breakdown" && groupColumn?.kind === "date" && (
          <label className="stats-field">
            <span>{t("statistics.granularity")}</span>
            <select value={granularity} onChange={(e) => onGranularity(e.target.value as Granularity)}>
              <option value="year">{t("statistics.by_year")}</option>
              <option value="month">{t("statistics.by_month")}</option>
              <option value="day">{t("statistics.by_day")}</option>
            </select>
          </label>
        )}

        {!draft && (
          <button type="button" className="stats-add-filter" onClick={startDraft}>
            <IconPlus />
            {t("statistics.add_filter")}
          </button>
        )}

        {isFetching && <span className="stats-inline-spinner" aria-hidden="true" />}
      </div>

      {draft && (
        <div className="stats-draft">
          <select
            value={draft.column}
            onChange={(e) => {
              const column = e.target.value;
              setDraft({ column, op: defaultOp(kinds[column]), value: "" });
            }}
          >
            {columns.map((c) => (
              <option key={c.name} value={c.name}>
                {columnLabel(c.name, lang)}
              </option>
            ))}
          </select>

          <select
            value={draft.op}
            onChange={(e) => setDraft({ ...draft, op: e.target.value as FilterOp })}
          >
            {(OPS_BY_KIND[kinds[draft.column]] ?? OPS_BY_KIND.text).map((op) => (
              <option key={op} value={op}>
                {t(`cleaning.op_${op}`)}
              </option>
            ))}
          </select>

          {!VALUELESS_OPS.has(draft.op) && (
            <div className="stats-draft-value">
              <ValueAutocomplete
                datasetId={datasetId}
                source={source}
                column={draft.column}
                value={String(draft.value ?? "")}
                onChange={(value) => setDraft({ ...draft, value })}
                placeholder={t("statistics.value_placeholder") ?? ""}
              />
            </div>
          )}

          <button type="button" className="stats-draft-apply" onClick={commitDraft}>
            {t("statistics.apply_filter")}
          </button>
          <button
            type="button"
            className="stats-draft-cancel"
            onClick={() => setDraft(null)}
            aria-label={t("filter.cancel")}
          >
            <IconClose />
          </button>
        </div>
      )}

      {filters.length > 0 && (
        <div className="stats-chips">
          {filters.map((f, i) => (
            <span className="stats-chip" key={`${f.column}-${f.op}-${i}`}>
              <strong>{columnLabel(f.column, lang)}</strong>
              <em>{t(`cleaning.op_${f.op}`)}</em>
              {!VALUELESS_OPS.has(f.op) && (
                <span className="stats-chip-value">
                  {translate ? translateValue(String(f.value ?? ""), lang) : String(f.value ?? "")}
                </span>
              )}
              <button
                type="button"
                onClick={() => onFilters(filters.filter((_, j) => j !== i))}
                aria-label={t("cleaning.remove")}
              >
                <IconClose />
              </button>
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function defaultOp(kind: string | undefined): FilterOp {
  return kind === "number" || kind === "date" ? "gte" : "eq";
}
