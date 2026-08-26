import { useTranslation } from "react-i18next";

import type { StatisticsOut } from "../../api/statistics";
import { formatCount, formatPercent } from "./labels";
import type { ChartRow } from "./rows";

/** Category cards beyond this are noise; the full list is in the table underneath. */
const MAX_CATEGORY_CARDS = 7;

interface Props {
  stats: StatisticsOut;
  rows: ChartRow[];
  onToggle: (key: string) => void;
}

/**
 * The headline figure and a card per category.
 *
 * The first card is the matching total and its share of the file - the denominator every
 * other card is a fraction of. The rest carry a count and a percentage each, in their
 * chart colour, and clicking one hides it from the charts just like the legend does.
 */
export default function KpiCards({ stats, rows, onToggle }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const share = stats.grand_total > 0 ? (stats.total * 100) / stats.grand_total : 0;

  return (
    <section className="stats-kpis">
      <article className="stats-kpi primary">
        <span className="stats-kpi-label">{t("statistics.matching_total")}</span>
        <strong className="stats-kpi-value">{formatCount(stats.total, lang)}</strong>
        <span className="stats-kpi-foot">
          {t("statistics.of_file", {
            share: formatPercent(share, lang),
            total: formatCount(stats.grand_total, lang),
          })}
        </span>
      </article>

      {rows.slice(0, MAX_CATEGORY_CARDS).map((r) => (
        <article
          key={r.key}
          className={r.hidden ? "stats-kpi off" : "stats-kpi"}
          style={{ "--kpi": r.color } as React.CSSProperties}
          onClick={() => onToggle(r.key)}
          title={t("statistics.toggle_hint") ?? ""}
        >
          <span className="stats-kpi-label" title={r.label}>
            {r.label}
          </span>
          <strong className="stats-kpi-value">{formatCount(r.count, lang)}</strong>
          <span className="stats-kpi-foot">
            <span className="stats-kpi-pct">{formatPercent(r.percentage, lang)}</span>
            <span className="stats-kpi-track">
              <span style={{ width: `${Math.min(100, r.percentage)}%`, background: r.color }} />
            </span>
          </span>
        </article>
      ))}
    </section>
  );
}
