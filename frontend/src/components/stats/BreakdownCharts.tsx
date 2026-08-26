import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";

import type { StatisticsOut } from "../../api/statistics";
import { columnLabel } from "../../data/columnDictionary";
import EChart from "./EChart";
import type { ChartHandle } from "./EChart";
import { IconChart, IconDonut, IconImage } from "./StatsIcons";
import { formatCount, formatPercent } from "./labels";
import type { ChartRow } from "./rows";
import { useThemeTokens } from "./useThemeTokens";

interface Props {
  stats: StatisticsOut;
  rows: ChartRow[];
  showPercent: boolean;
  onToggle: (key: string) => void;
  onShowAll: () => void;
}

export default function BreakdownCharts({ stats, rows, showPercent, onToggle, onShowAll }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const theme = useThemeTokens();
  const donutRef = useRef<ChartHandle>(null);
  const barRef = useRef<ChartHandle>(null);

  const visible = rows.filter((r) => !r.hidden);
  const columnName = columnLabel(stats.group_by, lang);

  // Long Hebrew colour names and trade names need room, so categories run down the side
  // and the bars run across. Years and histogram buckets are read as a sequence, so
  // those stay as columns.
  const horizontal = stats.mode === "value";

  // A horizontal bar chart is mirrored in Arabic and Hebrew: labels sit on the right and
  // the bars grow leftward, so a row is read label-first like every other line on the
  // page. Column charts are left alone - a time axis runs earliest-to-latest in both
  // directions, and flipping it would misread as running backwards.
  const rtl = i18n.dir(lang) === "rtl";

  const tooltip = useMemo(
    () => ({
      backgroundColor: theme.surface,
      borderColor: theme.border,
      borderWidth: 1,
      textStyle: { color: theme.text, fontSize: 12 },
      extraCssText: "box-shadow: 0 4px 16px -4px rgba(0,0,0,.18); border-radius: 8px;",
    }),
    [theme]
  );

  const donutOption = useMemo(
    () => ({
      tooltip: {
        trigger: "item",
        ...tooltip,
        formatter: (p: { data: { name: string; realCount: number; realPercent: number } }) =>
          [
            `<strong>${escapeHtml(p.data.name)}</strong>`,
            `${t("statistics.count")}: ${formatCount(p.data.realCount, lang)}`,
            `${t("statistics.share")}: ${formatPercent(p.data.realPercent, lang)}`,
          ].join("<br/>"),
      },
      series: [
        {
          type: "pie",
          radius: ["58%", "82%"],
          center: ["50%", "50%"],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: theme.surface, borderWidth: 2, borderRadius: 3 },
          label: { show: false },
          labelLine: { show: false },
          data: visible.map((r) => ({
            name: r.label,
            value: r.count,
            realCount: r.count,
            realPercent: r.percentage,
            itemStyle: { color: r.color },
          })),
        },
      ],
    }),
    [visible, theme, tooltip, t, lang]
  );

  const barOption = useMemo(() => {
    const labels = visible.map((r) => r.label);
    const values = visible.map((r) => (showPercent ? r.percentage : r.count));
    const valueAxis = {
      type: "value" as const,
      inverse: horizontal && rtl,
      axisLabel: {
        color: theme.muted,
        fontSize: 11,
        formatter: (v: number) => (showPercent ? `${v}%` : compact(v, lang)),
      },
      splitLine: { lineStyle: { color: theme.border, type: "dashed" as const } },
    };
    const categoryAxis = {
      type: "category" as const,
      data: labels,
      axisLabel: { color: theme.muted, fontSize: 11, interval: 0, hideOverlap: true },
      axisLine: { lineStyle: { color: theme.border } },
      axisTick: { show: false },
    };

    return {
      grid: { left: 4, right: 12, top: 8, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        ...tooltip,
        formatter: (params: { dataIndex: number }[]) => {
          const row = visible[params[0]?.dataIndex ?? 0];
          if (!row) return "";
          return [
            `<strong>${escapeHtml(row.label)}</strong>`,
            `${t("statistics.count")}: ${formatCount(row.count, lang)}`,
            `${t("statistics.share")}: ${formatPercent(row.percentage, lang)}`,
          ].join("<br/>");
        },
      },
      // a horizontal bar chart reads bottom-up, so the ranking is reversed to put the
      // largest category at the top where the eye starts
      xAxis: horizontal ? valueAxis : categoryAxis,
      yAxis: horizontal
        ? { ...categoryAxis, inverse: true, position: rtl ? ("right" as const) : ("left" as const) }
        : valueAxis,
      series: [
        {
          type: "bar",
          data: values.map((v, i) => ({ value: v, itemStyle: { color: visible[i].color } })),
          barMaxWidth: 26,
          itemStyle: {
            borderRadius: horizontal
              ? rtl
                ? [4, 0, 0, 4]
                : [0, 4, 4, 0]
              : [4, 4, 0, 0],
          },
        },
      ],
    };
  }, [visible, showPercent, horizontal, rtl, theme, tooltip, t, lang]);

  function download(handle: ChartHandle | null, suffix: string) {
    const url = handle?.toPng(theme.surface);
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = `${stats.group_by}-${suffix}.png`;
    a.click();
  }

  if (visible.length === 0) {
    return (
      <section className="stats-charts">
        <div className="stats-panel stats-panel-empty">
          <p>{t("statistics.all_hidden")}</p>
          <button type="button" className="stats-link" onClick={onShowAll}>
            {t("statistics.show_all_categories")}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="stats-charts">
      <div className="stats-panel">
        <header className="stats-panel-head">
          <h3>
            <IconDonut />
            {t("statistics.distribution_of", { column: columnName })}
          </h3>
          <button
            type="button"
            className="stats-icon-btn"
            onClick={() => download(donutRef.current, "donut")}
            title={t("statistics.export_png") ?? ""}
            aria-label={t("statistics.export_png") ?? ""}
          >
            <IconImage />
          </button>
        </header>
        <div className="stats-donut-wrap">
          <EChart
            option={donutOption}
            height={260}
            handleRef={donutRef}
            ariaLabel={t("statistics.distribution_of", { column: columnName }) ?? ""}
          />
          <div className="stats-donut-center">
            <strong>{compact(stats.total, lang)}</strong>
            <small>{t("statistics.records")}</small>
          </div>
        </div>
      </div>

      <div className="stats-panel">
        <header className="stats-panel-head">
          <h3>
            <IconChart />
            {t("statistics.comparison")}
          </h3>
          <button
            type="button"
            className="stats-icon-btn"
            onClick={() => download(barRef.current, "bars")}
            title={t("statistics.export_png") ?? ""}
            aria-label={t("statistics.export_png") ?? ""}
          >
            <IconImage />
          </button>
        </header>
        <EChart
          option={barOption}
          height={Math.max(260, horizontal ? visible.length * 26 + 40 : 260)}
          handleRef={barRef}
          ariaLabel={t("statistics.comparison") ?? ""}
        />
      </div>

      <div className="stats-panel stats-legend-panel">
        <header className="stats-panel-head">
          <h3>{t("statistics.legend")}</h3>
          {rows.some((r) => r.hidden) && (
            <button type="button" className="stats-link" onClick={onShowAll}>
              {t("statistics.show_all_categories")}
            </button>
          )}
        </header>
        <div className="stats-legend">
          {rows.map((r) => (
            <button
              type="button"
              key={r.key}
              className={r.hidden ? "stats-legend-item off" : "stats-legend-item"}
              onClick={() => onToggle(r.key)}
              aria-pressed={!r.hidden}
            >
              <span className="stats-swatch" style={{ background: r.color }} />
              <span className="stats-legend-label">{r.label}</span>
              <span className="stats-legend-value">
                {showPercent ? formatPercent(r.percentage, lang) : formatCount(r.count, lang)}
              </span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

/** 1,745,545 -> 1.7M. Axis ticks and the donut centre have no room for full figures. */
function compact(value: number, lang: string): string {
  return value.toLocaleString(lang, { notation: "compact", maximumFractionDigits: 1 });
}


/** Tooltips are built as HTML strings by ECharts, and category labels come from the
 *  file, so they are escaped rather than trusted. */
function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string
  );
}
