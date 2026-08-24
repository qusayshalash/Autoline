import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { PivotHeader, PivotOut } from "../../api/statistics";
import { columnLabel } from "../../data/columnDictionary";
import { translateValue } from "../../data/valueDictionary";
import { IconTable } from "./StatsIcons";
import { formatCount, formatMultiple, formatPercent } from "./labels";

/** How a cell's number is expressed. Row and column shares are what make a cross-tab
 *  answer comparative questions - "which maker leans electric" is a row share, not a
 *  count, because Kia and Toyota are not the same size. */
export type PivotMeasure = "count" | "row" | "column" | "total" | "lift";

/** Strongest tint any cell may take. See `tint` for why it is this low. */
const MAX_TINT_PERCENT = 28;

/**
 * How few rows a cell may be expected to hold before its lift stops being reported.
 *
 * Lift is a ratio, and a ratio over a tiny denominator is mostly noise: a cell expected
 * to hold 0.02 rows that happens to hold one reads as "50x", which describes the sparsity
 * of the crosstab rather than anything about the data. Five is the conventional floor for
 * treating an expected cell count as usable, and it is used here for the same reason.
 */
const MIN_EXPECTED = 5;

/** The ratio, either way up, at which the tint saturates. Beyond 4x over or under, cells
 *  stop getting darker - past that the exact figure is what matters, not the shade. */
const LIFT_TINT_CAP = 4;

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

  /**
   * How many rows this cell would hold if the two columns had nothing to do with each
   * other - the row's size times the column's size, over the grand total. Comparing the
   * real figure against it is what turns the matrix from a set of counts into a set of
   * findings: a cell at 3x is not merely large, it is larger than its own row and column
   * can account for.
   *
   * Returns null when the expectation is too small to divide by; see MIN_EXPECTED.
   */
  function lift(cell: number, rowTotal: number, colTotal: number): number | null {
    if (pivot.total <= 0) return null;
    const expected = (rowTotal * colTotal) / pivot.total;
    if (expected < MIN_EXPECTED) return null;
    return cell / expected;
  }

  function value(cell: number, rowTotal: number, colTotal: number): string {
    if (measure === "lift") {
      // Zero is reported rather than dashed away: a cell that could have held hundreds
      // of rows and holds none is one of the strongest things this view can say.
      const l = lift(cell, rowTotal, colTotal);
      return l === null ? "—" : formatMultiple(l, lang);
    }
    if (cell === 0) return "—";
    if (measure === "count") return formatCount(cell, lang);
    const base = measure === "row" ? rowTotal : measure === "column" ? colTotal : pivot.total;
    return base > 0 ? formatPercent((cell * 100) / base, lang) : "—";
  }

  /** 0..1, used only for shading. */
  function intensity(cell: number, rowTotal: number, colTotal: number): number {
    if (measure === "lift") {
      const l = lift(cell, rowTotal, colTotal);
      if (l === null) return 0;
      // Ratios are read in log space - 2x above and 2x below are the same distance from
      // neutral - so the tint is driven by the log, not by the raw difference. Without
      // it, everything under-represented would crowd into the bottom of the ramp while
      // over-representation took all of the top.
      if (l <= 0) return 1;
      return Math.min(1, Math.abs(Math.log2(l)) / Math.log2(LIFT_TINT_CAP));
    }
    if (cell === 0) return 0;
    if (measure === "count") return cell / maxCell;
    const base = measure === "row" ? rowTotal : measure === "column" ? colTotal : pivot.total;
    return base > 0 ? Math.min(1, cell / base) : 0;
  }

  /**
   * Which way a cell departs from its expectation, as a colour.
   *
   * Every other measure is a magnitude, and one hue says it. Lift is a direction as well:
   * 0.4x and 2.3x sit equally far from neutral and mean opposite things, so a single ramp
   * would render them alike. Blue carries over-represented, keeping the meaning it has in
   * the other measures; amber carries under-represented, being the token furthest from it
   * in hue that is defined in both themes. The pairing is also safe for the common forms
   * of colour blindness, which red and green would not be.
   */
  function hue(cell: number, rowTotal: number, colTotal: number): string {
    if (measure !== "lift") return "var(--primary)";
    const l = lift(cell, rowTotal, colTotal);
    return l !== null && l < 1 ? "var(--warning)" : "var(--primary)";
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

  /** The hover text. Under lift it also spells out the count and the expectation the
   *  ratio came from, so the multiple can be checked rather than taken on faith. */
  function cellTitle(cell: number, row: PivotHeader, col: PivotHeader | undefined): string {
    const where = `${label(row)} · ${col ? label(col) : ""}`;
    const count = `${where}: ${formatCount(cell, lang)}`;
    if (measure !== "lift" || !col) return count;
    const expected = pivot.total > 0 ? (row.total * col.total) / pivot.total : 0;
    if (expected < MIN_EXPECTED) return `${count}\n${t("pivot.lift_too_small")}`;
    return `${count}\n${t("pivot.lift_expected", {
      expected: expected.toLocaleString(lang, { maximumFractionDigits: 0 }),
    })}`;
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
                          ? {
                              background: `color-mix(in srgb, ${hue(
                                cell,
                                r.header.total,
                                col?.total ?? 0
                              )} ${tint(alpha)}%, transparent)`,
                            }
                          : undefined
                      }
                      title={cellTitle(cell, r.header, col)}
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
