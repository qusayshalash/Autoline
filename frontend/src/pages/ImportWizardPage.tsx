import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { apiErrorMessage, getDataset, getJob, repreviewDataset, startImport, type UploadResponse } from "../api/client";
import Breadcrumb from "../components/Breadcrumb";
import ErrorBanner from "../components/ErrorBanner";

const DELIMITERS = [
  { value: ",", labelKey: "import_wizard.delimiter_comma" },
  { value: ";", labelKey: "import_wizard.delimiter_semicolon" },
  { value: "|", labelKey: "import_wizard.delimiter_pipe" },
  { value: "\t", labelKey: "import_wizard.delimiter_tab" },
];

export default function ImportWizardPage() {
  const { t } = useTranslation();
  const { datasetId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: dataset } = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => getDataset(datasetId),
  });

  const [encoding, setEncoding] = useState("utf-8");
  const [delimiter, setDelimiter] = useState(",");
  const [hasHeader, setHasHeader] = useState(true);
  const [preview, setPreview] = useState<UploadResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const previewMutation = useMutation({
    mutationFn: () => repreviewDataset(datasetId, { encoding, delimiter, has_header: hasHeader }),
    onSuccess: (res) => {
      setPreview(res);
      setPreviewError(null);
    },
    onError: (err) => setPreviewError(apiErrorMessage(err, t("common.error_generic"))),
  });

  useEffect(() => {
    if (dataset && !preview) {
      const initialEncoding = dataset.encoding || "utf-8";
      const initialDelimiter = dataset.delimiter || ",";
      const initialHasHeader = dataset.has_header ?? true;
      setEncoding(initialEncoding);
      setDelimiter(initialDelimiter);
      setHasHeader(initialHasHeader);
      repreviewDataset(datasetId, {
        encoding: initialEncoding,
        delimiter: initialDelimiter,
        has_header: initialHasHeader,
      })
        .then((res) => {
          setPreview(res);
          setPreviewError(null);
        })
        .catch((err) => setPreviewError(apiErrorMessage(err, t("common.error_generic"))));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset]);

  const [importError, setImportError] = useState<string | null>(null);

  const importMutation = useMutation({
    mutationFn: () => startImport(datasetId, { encoding, delimiter, has_header: hasHeader }),
    onSuccess: (job) => {
      setJobId(job.id);
      setImportError(null);
    },
    onError: (err) => setImportError(apiErrorMessage(err, t("common.error_generic"))),
  });

  const { data: job } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data?.status === "done" || q.state.data?.status === "error" ? false : 1000),
    refetchIntervalInBackground: true,
  });

  useEffect(() => {
    if (job?.status === "done") {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["dataset", datasetId] });
    }
  }, [job?.status, qc, datasetId]);

  return (
    <div>
      <Breadcrumb
        items={[
          { label: t("nav.datasets"), to: "/" },
          { label: dataset?.original_filename ?? "…" },
          { label: t("import_wizard.title") },
        ]}
      />
      <h2>{t("import_wizard.title")}</h2>
      <div className="card">
        <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
          <div className="field">
            <label>{t("import_wizard.detected_encoding")}</label>
            <input type="text" value={encoding} onChange={(e) => setEncoding(e.target.value)} />
          </div>
          <div className="field">
            <label>{t("import_wizard.detected_delimiter")}</label>
            <select value={delimiter} onChange={(e) => setDelimiter(e.target.value)}>
              {DELIMITERS.map((d) => (
                <option key={d.value} value={d.value}>
                  {t(d.labelKey)}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>{t("import_wizard.has_header")}</label>
            <input type="checkbox" checked={hasHeader} onChange={(e) => setHasHeader(e.target.checked)} />
          </div>
        </div>
        <button className="btn secondary" onClick={() => previewMutation.mutate()} disabled={previewMutation.isPending}>
          {t("import_wizard.re_preview")}
        </button>
        <ErrorBanner message={previewError} />
      </div>

      {preview && (
        <div className="card">
          <h3>{t("import_wizard.preview")}</h3>
          <p className="muted">
            {t("import_wizard.columns")}: {preview.columns.length}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {preview.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.preview_rows.slice(0, 15).map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        {!jobId && (
          <>
            <button className="btn" onClick={() => importMutation.mutate()} disabled={importMutation.isPending}>
              {t("import_wizard.start_import")}
            </button>
            <ErrorBanner message={importError} />
          </>
        )}

        {job && job.status !== "done" && job.status !== "error" && (
          <div>
            <p>{t("import_wizard.importing")}</p>
            <p className="muted">
              {job.progress.startsWith("normalizing:")
                ? t("import_wizard.normalizing_progress", { count: job.progress.split(":")[1] })
                : job.progress}
            </p>
          </div>
        )}

        {job?.status === "done" && (
          <div>
            <p style={{ color: "var(--success)", fontWeight: 600 }}>
              {t("import_wizard.done")} ({(job.result?.row_count as number)?.toLocaleString()})
            </p>
            <div style={{ display: "flex", gap: "0.6rem" }}>
              <button className="btn" onClick={() => navigate(`/datasets/${datasetId}/explore`)}>
                {t("nav.explorer")}
              </button>
              <button className="btn secondary" onClick={() => navigate(`/datasets/${datasetId}/clean`)}>
                {t("nav.cleaning")}
              </button>
            </div>
          </div>
        )}

        {job?.status === "error" && (
          <p style={{ color: "var(--danger)" }}>
            {t("import_wizard.error")}: {job.error_message}
          </p>
        )}
      </div>
    </div>
  );
}
