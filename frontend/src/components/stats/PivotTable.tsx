import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { PivotHeader, PivotOut } from "../../api/statistics";
import { columnLabel } from "../../data/columnDictionary";
import { translateValue } from "../../data/valueDictionary";
import { IconTable } from "./StatsIcons";
import { formatCount, formatPercent } from "./labels";

/** How a cell's number is expressed. Row and column shares are what make a cross-tab
 *  answer comparative questions - "which maker leans electric" is a row share, not a
 *  count, because Kia and Toyota are not the same size. */
export type PivotMeasure = "count" | "row" | "column" | "total";

/** Strongest tint any cell may take. See `tint` for why it is this low. */
const MAX_TINT_PERCENT = 28;

interface Props {
  pivot: PivotOut;
  measure: PivotMeasure;
  translate: boolean;
}

/**
 * The matrix.
 *
 * Shaded by value so the pattern is visible before any number is read: the eye finds the
 * dark corner, then the figure confirms it. Shading is always relative to whatever is
 * being shown - counts shade against the largest cell, row shares against 100% of a row -
 * so the colour never implies a comparison the numbers do not support.
 */
export default function PivotTable({ pivot, measure, translate }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const label = (h: PivotHeader) => {
    if (h.other) return t("statistics.other");
    if (h.unspecified) return t("statistics.unspecified");
    return translate ? translateValue(h.value, lang) : h.value;
  };

  const maxCell = useMemo(
    () => Math.max(1, ...pivot.rows.flatMap((r) => r.cells)),
    [pivot]
  );

  function value(cell: number, rowTotal: number, colTotal: number): string {
    if (cell === 0) return "—";
    if (measure === "count") return formatCount(cell, lang);
    const base = measure === "row" ? rowTotal : measure === "column" ? colTotal : pivot.total;
    return base > 0 ? formatPercent((cell * 100) / base, lang) : "—";
  }

  /** 0..1, used only for shading. */
  function intensity(cell: number, rowTotal: number, colTotal: number): number {
    if (cell === 0) return 0;
    if (measure === "count") return cell / maxCell;
    const base = measure === "row" ? rowTotal : measure === "column" ? colTotal : pivot.total;
    return base > 0 ? Math.min(1, cell / base) : 0;
  }

  /**
   * Tint strength for a cell, as a percentage of the accent colour.
   *
   * Capped well below full: a mid-strength blue is the one background that fails both
   * themes at once - too dark for the light theme's near-black text, too light for the
   * dark theme's near-white text. Measured at full strength the text came out at 2.5:1.
   * Held under a third, both themes clear 4.5:1 comfortably.
   *
   * The square root spends that narrow range where it is needed: small differences among
   * the many small cells are visible, instead of every one of them washing out to nearly
   * nothing while the single largest cell takes the whole ramp.
   */
  function tint(value: number): number {
    return Math.round(Math.sqrt(value) * MAX_TINT_PERCENT);
  }

  return (
    <section className="stats-panel pivot-panel">
      <header className="stats-panel-head">
        <h3>
          <IconTable />
          {t("pivot.matrix_title", {
            rows: columnLabel(pivot.row_column, lang),
            columns: columnLabel(pivot.column_column, lang),
          })}
        </h3>
        <span className="stats-panel-note">
          {t("pivot.shape", {
            rows: pivot.distinct_rows.toLocaleString(lang),
            columns: pivot.distinct_columns.toLocaleString(lang),
          })}
        </span>
      </header>

      {(pivot.rows_truncated || pivot.columns_truncated) && (
        <p className="pivot-note">{t("pivot.folded_note")}</p>
      )}

      <div className="pivot-scroll">
        <table className="pivot-table">
          <thead>
            <tr>
              <th className="pivot-corner">{columnLabel(pivot.row_column, lang)}</th>
              {pivot.columns.map((c, i) => (
                <th key={`${c.value}-${i}`} className={c.other ? "is-other" : undefined}>
                  <span title={label(c)}>{label(c)}</span>
                  <small>{formatCount(c.total, lang)}</small>
                </th>
              ))}
              <th className="pivot-total-head">{t("statistics.total")}</th>
            </tr>
          </thead>
          <tbody>
            {pivot.rows.map((r, ri) => (
              <tr key={`${r.header.value}-${ri}`} className={r.header.other ? "is-other" : undefined}>
                <th scope="row" title={label(r.header)}>
                  {label(r.header)}
                </th>
                {r.cells.map((cell, ci) => {
                  const col = pivot.columns[ci];
                  // The "other" bands are aggregates of many categories at once, so
                  // shading them would invite a comparison against single-category cells
                  // that the number does not support. They stay plain.
                  const aggregate = r.header.other || col?.other;
                  const alpha = aggregate ? 0 : intensity(cell, r.header.total, col?.total ?? 0);
                  return (
                    <td
                      key={ci}
                      className={cell === 0 ? "is-zero" : undefined}
                      style={
                        alpha > 0
                          ? { background: `color-mix(in srgb, var(--primary) ${tint(alpha)}%, transparent)` }
                          : undefined
                      }
                      title={`${label(r.header)} · ${col ? label(col) : ""}: ${formatCount(cell, lang)}`}
                    >
                      {value(cell, r.header.total, col?.total ?? 0)}
                    </td>
                  );
                })}
                <td className="pivot-total">{formatCount(r.header.total, lang)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th>{t("statistics.total")}</th>
              {pivot.columns.map((c, i) => (
                <td key={i} className="pivot-total">
                  {formatCount(c.total, lang)}
                </td>
              ))}
              <td className="pivot-total pivot-grand">{formatCount(pivot.total, lang)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}
