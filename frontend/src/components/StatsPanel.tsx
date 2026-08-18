import { useTranslation } from "react-i18next";

import type { StatsOut } from "../api/client";

function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${units[i]}`;
}

export default function StatsPanel({ stats }: { stats: StatsOut }) {
  const { t } = useTranslation();
  return (
    <div className="stat-grid">
      <div className="stat-tile">
        <div className="value">{stats.row_count_raw.toLocaleString()}</div>
        <div className="label">{t("stats.row_count_raw")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{stats.row_count_cleaned?.toLocaleString() ?? "-"}</div>
        <div className="label">{t("stats.row_count_cleaned")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{stats.duplicates_removed.toLocaleString()}</div>
        <div className="label">{t("stats.duplicates_removed")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{stats.filtered_out.toLocaleString()}</div>
        <div className="label">{t("stats.filtered_out")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{formatBytes(stats.raw_file_bytes)}</div>
        <div className="label">{t("stats.raw_size")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{formatBytes(stats.cleaned_file_bytes)}</div>
        <div className="label">{t("stats.cleaned_size")}</div>
      </div>
      <div className="stat-tile">
        <div className="value">{stats.reduction_pct !== null ? `${stats.reduction_pct}%` : "-"}</div>
        <div className="label">{t("stats.reduction_pct")}</div>
      </div>
    </div>
  );
}
