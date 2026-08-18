import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { apiErrorMessage, applyCleaning, getDataset, type CleaningResult, type FilterRule } from "../api/client";
import Breadcrumb from "../components/Breadcrumb";
import ErrorBanner from "../components/ErrorBanner";
import FilterBuilder from "../components/FilterBuilder";
import LoadingState from "../components/LoadingState";

function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${units[i]}`;
}

export default function CleaningPage() {
  const { t } = useTranslation();
  const { datasetId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: dataset } = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => getDataset(datasetId),
  });

  const [keepColumns, setKeepColumns] = useState<string[]>([]);
  const [dedupe, setDedupe] = useState(false);
  const [dedupeKeyColumns, setDedupeKeyColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<FilterRule[]>([]);
  const [result, setResult] = useState<CleaningResult | null>(null);

  useEffect(() => {
    if (dataset && keepColumns.length === 0) setKeepColumns(dataset.columns);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset]);

  const cleanMutation = useMutation({
    mutationFn: () =>
      applyCleaning(datasetId, {
        keep_columns: keepColumns,
        dedupe,
        dedupe_key_columns: dedupeKeyColumns.length > 0 ? dedupeKeyColumns : null,
        filters,
      }),
    onSuccess: (res) => {
      setResult(res);
      qc.invalidateQueries({ queryKey: ["dataset", datasetId] });
      qc.invalidateQueries({ queryKey: ["datasets"] });
    },
  });

  function toggleColumn(col: string) {
    setKeepColumns((prev) => (prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]));
  }

  function toggleDedupeKey(col: string) {
    setDedupeKeyColumns((prev) => (prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]));
  }

  if (!dataset) return <LoadingState />;

  return (
    <div>
      <Breadcrumb
        items={[
          { label: t("nav.datasets"), to: "/" },
          { label: dataset.original_filename },
          { label: t("cleaning.title") },
        ]}
      />
      <h2>{t("cleaning.title")}</h2>

      <div className="card">
        <h3>{t("cleaning.select_columns")}</h3>
        <div className="toolbar">
          <button className="btn secondary" onClick={() => setKeepColumns(dataset.columns)}>
            {t("cleaning.select_all")}
          </button>
          <button className="btn secondary" onClick={() => setKeepColumns([])}>
            {t("cleaning.clear_all")}
          </button>
        </div>
        <div className="column-picker">
          {dataset.columns.map((c) => (
            <button
              key={c}
              type="button"
              className={`column-chip${keepColumns.includes(c) ? " selected" : ""}`}
              onClick={() => toggleColumn(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <label>
          <input type="checkbox" checked={dedupe} onChange={(e) => setDedupe(e.target.checked)} />{" "}
          {t("cleaning.dedupe")}
        </label>
        {dedupe && (
          <div style={{ marginTop: "0.6rem" }}>
            <p className="muted">{t("cleaning.dedupe_key")}</p>
            <div className="column-picker">
              {dataset.columns.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`column-chip${dedupeKeyColumns.includes(c) ? " selected" : ""}`}
                  onClick={() => toggleDedupeKey(c)}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h3>{t("cleaning.filters")}</h3>
        {/* cleaning always runs against the raw table, so suggest raw values */}
        <FilterBuilder
          columns={dataset.columns}
          filters={filters}
          onChange={setFilters}
          datasetId={datasetId}
          source="raw"
        />
      </div>

      <div className="card">
        <button
          className="btn"
          onClick={() => cleanMutation.mutate()}
          disabled={cleanMutation.isPending || keepColumns.length === 0}
        >
          {cleanMutation.isPending ? t("cleaning.applying") : t("cleaning.apply")}
        </button>
        {keepColumns.length === 0 && <p className="muted">{t("cleaning.no_columns_hint")}</p>}

        <ErrorBanner
          message={cleanMutation.isError ? apiErrorMessage(cleanMutation.error, t("common.error_generic")) : null}
        />

        {result && (
          <div style={{ marginTop: "1rem" }}>
            <h3>{t("cleaning.result_title")}</h3>
            <div className="stat-grid">
              <div className="stat-tile">
                <div className="value">{result.rows_before.toLocaleString()}</div>
                <div className="label">{t("cleaning.rows_before")}</div>
              </div>
              <div className="stat-tile">
                <div className="value">{result.rows_after.toLocaleString()}</div>
                <div className="label">{t("cleaning.rows_after")}</div>
              </div>
              <div className="stat-tile">
                <div className="value">{result.duplicates_removed.toLocaleString()}</div>
                <div className="label">{t("cleaning.duplicates_removed")}</div>
              </div>
              <div className="stat-tile">
                <div className="value">{result.filtered_out.toLocaleString()}</div>
                <div className="label">{t("cleaning.filtered_out")}</div>
              </div>
              <div className="stat-tile">
                <div className="value">{result.reduction_pct}%</div>
                <div className="label">{t("cleaning.reduction")}</div>
              </div>
              <div className="stat-tile">
                <div className="value">{formatBytes(result.cleaned_file_bytes)}</div>
                <div className="label">{t("stats.cleaned_size")}</div>
              </div>
            </div>
            {result.columns_dropped.length > 0 && (
              <p className="muted">
                {t("cleaning.columns_dropped")}: {result.columns_dropped.join(", ")}
              </p>
            )}
            <button className="btn" style={{ marginTop: "0.6rem" }} onClick={() => navigate(`/datasets/${datasetId}/explore`)}>
              {t("nav.explorer")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
