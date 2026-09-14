import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useConfirm } from "../components/ConfirmProvider";
import { useNavigate } from "react-router-dom";

import { apiErrorMessage, deleteDataset, listDatasets, renameDataset, uploadDataset } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import QualityReportView from "../components/QualityReportView";
import UploadDropzone from "../components/UploadDropzone";

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${units[i]}`;
}

export default function DatasetsPage() {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { can } = useAuth();
  const canUpload = can("datasets.upload");
  const canDelete = can("datasets.delete");
  const canRunQuality = can("datasets.view");
  // The permission set has no separate "rename" key - renaming is a metadata edit in the
  // same class as cleaning, which is already the "update" permission for datasets, so it
  // rides on that instead of adding a permission for one small screen.
  const canRename = can("datasets.clean");
  const [progress, setProgress] = useState(0);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  // which dataset's import report is expanded, if any
  const [quality, setQualityFor] = useState<string | null>(null);

  const { data: datasets, isLoading } = useQuery({
    queryKey: ["datasets"],
    queryFn: listDatasets,
    refetchInterval: 4000,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadDataset(file, setProgress),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      navigate(`/datasets/${res.dataset_id}/import`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDataset,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setDeleteError(null);
    },
    onError: (err) => setDeleteError(apiErrorMessage(err, t("common.error_generic"))),
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameDataset(id, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setRenamingId(null);
      setRenameError(null);
    },
    onError: (err) => setRenameError(apiErrorMessage(err, t("common.error_generic"))),
  });

  function startRename(id: string, currentName: string) {
    setRenamingId(id);
    setRenameValue(currentName);
    setRenameError(null);
  }

  function commitRename(id: string) {
    const name = renameValue.trim();
    if (!name) {
      setRenamingId(null);
      return;
    }
    renameMutation.mutate({ id, name });
  }

  function statusBadgeClass(status: string) {
    if (status === "ready") return "ready";
    if (status === "error") return "error";
    return "pending";
  }

  return (
    <div>
      <h2>{t("datasets.title")}</h2>
      {canUpload && (
        <div className="card">
          <UploadDropzone
            busy={uploadMutation.isPending}
            progress={progress}
            onFile={(file) => uploadMutation.mutate(file)}
          />
          <ErrorBanner
            message={uploadMutation.isError ? apiErrorMessage(uploadMutation.error, t("common.error_generic")) : null}
          />
        </div>
      )}
      <ErrorBanner message={deleteError} />
      <ErrorBanner message={renameError} />

      {isLoading ? (
        <div className="dataset-list">
          {[0, 1, 2].map((i) => (
            <div className="skeleton skeleton-row" key={i} />
          ))}
        </div>
      ) : !datasets || datasets.length === 0 ? (
        <EmptyState message={t("datasets.empty")} />
      ) : (
        <div className="dataset-list">
          {datasets.map((d) => (
            <div className="dataset-row" key={d.id}>
              <div>
                {renamingId === d.id ? (
                  <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                    <input
                      type="text"
                      aria-label={t("datasets.rename") ?? ""}
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitRename(d.id);
                        if (e.key === "Escape") setRenamingId(null);
                      }}
                      disabled={renameMutation.isPending}
                    />
                    <button
                      type="button"
                      className="btn secondary small"
                      disabled={renameMutation.isPending}
                      onClick={() => commitRename(d.id)}
                    >
                      {t("common.save")}
                    </button>
                    <button
                      type="button"
                      className="btn secondary small"
                      disabled={renameMutation.isPending}
                      onClick={() => setRenamingId(null)}
                    >
                      {t("common.cancel")}
                    </button>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                    <span style={{ fontWeight: 600 }}>{d.original_filename}</span>
                    {canRename && (
                      <button
                        type="button"
                        className="linkish"
                        onClick={() => startRename(d.id, d.original_filename)}
                      >
                        {t("datasets.rename")}
                      </button>
                    )}
                  </div>
                )}
                <div className="muted">
                  {t("datasets.rows_raw")}: {d.row_count_raw?.toLocaleString() ?? "-"} ·{" "}
                  {t("datasets.rows_cleaned")}: {d.row_count_cleaned?.toLocaleString() ?? "-"} ·{" "}
                  {t("datasets.size")}: {formatBytes(d.raw_file_bytes)}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                {d.quality_verdict && (
                  <button
                    type="button"
                    className={`quality-badge verdict-${d.quality_verdict}`}
                    onClick={() => setQualityFor(quality === d.id ? null : d.id)}
                    title={t(`quality.verdict_hint.${d.quality_verdict}`) ?? ""}
                  >
                    {t(`quality.verdict.${d.quality_verdict}`)}
                  </button>
                )}
                <span className={`badge ${statusBadgeClass(d.status)}`}>
                  {t(`datasets.status_${d.status}`, d.status)}
                </span>
                {d.status === "ready" ? (
                  <>
                    <button
                      className="btn secondary"
                      onClick={() => navigate(`/datasets/${d.id}/profile`)}
                    >
                      {t("profile.title")}
                    </button>
                    <button className="btn secondary" onClick={() => navigate(`/datasets/${d.id}/explore`)}>
                      {t("datasets.open")}
                    </button>
                  </>
                ) : d.status === "preview" && canUpload ? (
                  <button className="btn secondary" onClick={() => navigate(`/datasets/${d.id}/import`)}>
                    {t("import_wizard.title")}
                  </button>
                ) : null}
                {canDelete && (
                  <button
                    className="btn danger"
                    onClick={async () => {
                      if (await confirm({ body: t("datasets.confirm_delete") })) {
                        deleteMutation.mutate(d.id);
                      }
                    }}
                  >
                    {t("datasets.delete")}
                  </button>
                )}
                {d.status === "ready" && !d.quality_verdict && (
                  <button
                    type="button"
                    className="btn secondary"
                    onClick={() => setQualityFor(quality === d.id ? null : d.id)}
                  >
                    {t("quality.check")}
                  </button>
                )}
              </div>
            </div>
          ))}
          {quality && (
            <div className="dataset-quality">
              <QualityReportView datasetId={quality} canRun={canRunQuality} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
