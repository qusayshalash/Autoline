import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { apiErrorMessage, deleteDataset, listDatasets } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconFiles, IconSearch, IconTrash } from "../../components/admin/AdminIcons";
import { AdminPanel, formatBytes, formatDateTime } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";
import LoadingState from "../../components/LoadingState";

export default function FilesPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: datasets, isLoading } = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });

  const remove = useMutation({
    mutationFn: (id: string) => deleteDataset(id),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
      qc.invalidateQueries({ queryKey: ["admin-activity"] });
      qc.invalidateQueries({ queryKey: ["admin-system"] });
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return datasets ?? [];
    return (datasets ?? []).filter((d) => d.original_filename.toLowerCase().includes(q));
  }, [datasets, search]);

  const totalBytes = (datasets ?? []).reduce((sum, d) => sum + (d.raw_file_bytes ?? 0), 0);

  if (isLoading) return <LoadingState />;

  return (
    <div className="admin-page">
      <AdminPanel
        icon={<IconFiles />}
        title={t("admin.files.title", { count: filtered.length })}
        actions={<span className="muted">{formatBytes(totalBytes)}</span>}
      >
        <div className="admin-toolbar">
          <span className="admin-search">
            <IconSearch />
            <input
              type="search"
              value={search}
              placeholder={t("admin.files.search") ?? ""}
              onChange={(e) => setSearch(e.target.value)}
            />
          </span>
        </div>

        <ErrorBanner message={error} />

        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t("admin.files.name")}</th>
                <th>{t("admin.files.status")}</th>
                <th>{t("admin.files.rows")}</th>
                <th>{t("admin.files.columns")}</th>
                <th>{t("admin.files.size")}</th>
                <th>{t("admin.files.created")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link to={`/datasets/${d.id}/explore`} className="cell-link">
                      {d.original_filename}
                    </Link>
                  </td>
                  <td>
                    <span className={`status-pill status-${d.status === "ready" ? "active" : "pending"}`}>
                      {t(`datasets.status_${d.status}`, { defaultValue: d.status })}
                    </span>
                  </td>
                  <td className="mono">{(d.row_count_raw ?? 0).toLocaleString()}</td>
                  <td className="mono">{d.columns?.length ?? 0}</td>
                  <td className="mono">{formatBytes(d.raw_file_bytes)}</td>
                  <td>{formatDateTime(d.created_at)}</td>
                  <td className="row-actions">
                    {can("datasets.delete") && (
                      <button
                        className="link-btn danger"
                        onClick={() => {
                          if (window.confirm(t("datasets.confirm_delete") ?? "")) remove.mutate(d.id);
                        }}
                      >
                        <IconTrash />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted empty-row">
                    {t("datasets.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </AdminPanel>
    </div>
  );
}
