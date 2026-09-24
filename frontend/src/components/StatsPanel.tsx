import { useTranslation } from "react-i18next";

import type { StatsOut } from "../api/client";
import { formatBytes, formatNumber } from "../data/numbers";


export default function StatsPanel({ stats }: { stats: StatsOut }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  return (
    <div className="stat-grid">
      <div className="stat-tile">
        <div className="value">{formatNumber(stats.row_count_raw, lang)}</div>
        <div className="label">{t("stats.row_count_raw")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{formatNumber(stats.row_count_cleaned, lang)}</div>
        <div className="label">{t("stats.row_count_cleaned")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{formatNumber(stats.duplicates_removed, lang)}</div>
        <div className="label">{t("stats.duplicates_removed")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{formatNumber(stats.filtered_out, lang)}</div>
        <div className="label">{t("stats.filtered_out")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{formatBytes(stats.raw_file_bytes, lang)}</div>
        <div className="label">{t("stats.raw_size")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{formatBytes(stats.cleaned_file_bytes, lang)}</div>
        <div className="label">{t("stats.cleaned_size")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{stats.reduction_pct !== null ? `${stats.reduction_pct}%` : "-"}</div>
        <div className="label">{t("stats.reduction_pct")}</div>
      </div>
    </div>
  );
}
