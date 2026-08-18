import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, Navigate } from "react-router-dom";

import { listDatasets } from "../api/client";
import { IconChart } from "../components/stats/StatsIcons";

/**
 * `/statistics` with no file chosen.
 *
 * With exactly one imported file there is nothing to choose, so it opens straight away.
 * With several, the choice is the page.
 */
export default function StatisticsIndexPage() {
  const { t, i18n } = useTranslation();
  const { data: datasets, isLoading } = useQuery({
    queryKey: ["datasets"],
    queryFn: listDatasets,
  });

  if (isLoading) return <p className="muted">{t("common.loading")}</p>;

  const ready = (datasets ?? []).filter((d) => d.status === "ready");
  if (ready.length === 1) return <Navigate to={`/statistics/${ready[0].id}`} replace />;

  if (ready.length === 0) {
    return (
      <div className="stats-empty">
        <h3>{t("statistics.no_files")}</h3>
        <p>{t("statistics.no_files_hint")}</p>
        <Link className="stats-link" to="/">
          {t("statistics.back_to_data")}
        </Link>
      </div>
    );
  }

  return (
    <div className="stats-picker">
      <h3>{t("statistics.pick_file")}</h3>
      <div className="stats-picker-grid">
        {ready.map((d) => (
          <Link key={d.id} to={`/statistics/${d.id}`} className="stats-picker-card">
            <span className="stats-picker-icon">
              <IconChart />
            </span>
            <strong>{d.original_filename}</strong>
            <small>
              {(d.row_count_cleaned ?? d.row_count_raw ?? 0).toLocaleString(i18n.language)}{" "}
              {t("explorer.rows")} · {d.columns.length} {t("sheet.cols")}
            </small>
          </Link>
        ))}
      </div>
    </div>
  );
}
