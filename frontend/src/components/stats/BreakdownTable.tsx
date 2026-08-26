import { useTranslation } from "react-i18next";

import { IconTable } from "./StatsIcons";
import { formatCount, formatPercent } from "./labels";
import type { ChartRow } from "./rows";

interface Props {
  rows: ChartRow[];
  total: number;
  onToggle: (key: string) => void;
}

/**
 * The numbers behind the charts.
 *
 * Every row carries its chart colour, so a slice can be traced to a figure without
 * counting round the donut, and hidden categories stay listed (greyed) rather than
 * disappearing - otherwise hiding one would look like losing data.
 */
export default function BreakdownTable({ rows, total, onToggle }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const max = Math.max(1, ...rows.map((r) => r.count));

  return (
    <section className="stats-panel stats-table-panel">
      <header className="stats-panel-head">
        <h3>
          <IconTable />
          {t("statistics.details")}
        </h3>
        <span className="stats-panel-note">
          {t("statistics.rows_in_table", { count: rows.length })}
        </span>
      </header>

      <div className="stats-table-scroll">
        <table className="stats-table">
          <thead>
            <tr>
              <th className="col-swatch" aria-label={t("statistics.colour") ?? ""} />
              <th>{t("statistics.value")}</th>
              <th className="num">{t("statistics.count")}</th>
              <th className="num">{t("statistics.share")}</th>
              <th className="col-bar">{t("statistics.distribution")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.key}
                className={r.hidden ? "hidden-row" : undefined}
                onClick={() => onToggle(r.key)}
                title={t("statistics.toggle_hint") ?? ""}
              >
                <td className="col-swatch">
                  <span className="stats-swatch" style={{ background: r.color }} />
                </td>
                <td className="col-value" title={r.label}>
                  {r.label}
                </td>
                <td className="num">{formatCount(r.count, lang)}</td>
                <td className="num strong">{formatPercent(r.percentage, lang)}</td>
                <td className="col-bar">
                  <span className="stats-minibar">
                    <span style={{ width: `${(r.count / max) * 100}%`, background: r.color }} />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td />
              <td>{t("statistics.total")}</td>
              <td className="num strong">{formatCount(total, lang)}</td>
              <td className="num strong">{formatPercent(sum(rows), lang)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}

/** The listed shares, added up as shown. Each is rounded to two decimals server-side, so
 *  this lands within a hundredth of 100% rather than exactly on it - showing the real
 *  sum is more honest than printing "100%" regardless. */
function sum(rows: ChartRow[]): number {
  return rows.reduce((acc, r) => acc + r.percentage, 0);
}
