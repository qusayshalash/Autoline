import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { CleanupOptions } from "../../api/admin";
import { fetchCleanupPlan, fetchStorage, runCleanup, setRetention } from "../../api/admin";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconDatabase, IconTrash } from "../../components/admin/AdminIcons";
import { AdminPanel, formatBytes } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";
import LoadingState from "../../components/LoadingState";

const RETENTION_CHOICES = [0, 24, 72, 168, 720];

/**
 * Storage, and the only place in the app that deletes files.
 *
 * Nothing here removes anything until the exact list has been fetched and shown - the
 * server answers "what would go" and "go" through separate endpoints for that reason.
 * Originals and databases are refused server-side whatever this screen asks for, so the
 * worst a mistake here can cost is a re-export.
 */
export default function StoragePanel() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();

  const [options, setOptions] = useState<CleanupOptions>({
    expired_exports: true,
    all_exports: false,
    intermediates: true,
  });
  const [preview, setPreview] = useState<null | Awaited<ReturnType<typeof fetchCleanupPlan>>>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const { data: storage, isLoading } = useQuery({
    queryKey: ["admin-storage"],
    queryFn: fetchStorage,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-storage"] });
    queryClient.invalidateQueries({ queryKey: ["admin-system"] });
  };

  const retention = useMutation({
    mutationFn: setRetention,
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const cleanup = useMutation({
    mutationFn: () => runCleanup(options),
    onSuccess: (r) => {
      setPreview(null);
      setDone(
        t("admin.storage.cleaned", {
          count: r.removed_files,
          size: formatBytes(r.freed_bytes),
        })
      );
      refresh();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  async function showPreview() {
    setError(null);
    setDone(null);
    try {
      setPreview(await fetchCleanupPlan(options));
    } catch (e) {
      setError(apiErrorMessage(e, t("common.error_generic")));
    }
  }

  if (isLoading || !storage) return <LoadingState />;

  const canClean = can("datasets.delete");
  const previewBytes = preview?.reduce((a, p) => a + p.bytes, 0) ?? 0;

  return (
    <AdminPanel
      icon={<IconDatabase />}
      title={t("admin.storage.title")}
      note={t("admin.storage.total", { size: formatBytes(storage.total_bytes) })}
    >
      <ErrorBanner message={error} />

      <div className="storage-bars">
        {storage.categories
          .filter((c) => c.bytes > 0)
          .map((c) => (
            <div key={c.key} className="storage-row">
              <span className="storage-name">
                {t(`admin.storage.category.${c.key}`)}
                {!c.removable && <em className="storage-lock">{t("admin.storage.protected")}</em>}
              </span>
              <span className="storage-bar">
                <span
                  className={c.removable ? "removable" : ""}
                  style={{ width: `${(c.bytes / Math.max(1, storage.total_bytes)) * 100}%` }}
                />
              </span>
              <span className="storage-size">{formatBytes(c.bytes)}</span>
            </div>
          ))}
      </div>

      <p className="muted admin-note">{t("admin.storage.what_is_what")}</p>

      <dl className="detail-list">
        <div>
          <dt>{t("admin.storage.reclaimable")}</dt>
          <dd>
            {formatBytes(storage.reclaimable_bytes)}
            {storage.reclaimable_files > 0 && (
              <span className="muted"> · {storage.reclaimable_files}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>{t("admin.storage.disk_free")}</dt>
          <dd>{formatBytes(storage.disk_free_bytes)}</dd>
        </div>
        <div>
          <dt>{t("admin.storage.data_dir")}</dt>
          <dd className="mono wrap">{storage.data_dir}</dd>
        </div>
      </dl>

      <p className="drawer-section">{t("admin.storage.retention")}</p>
      <p className="muted admin-note">{t("admin.storage.retention_hint")}</p>
      <div className="storage-retention">
        {RETENTION_CHOICES.map((h) => (
          <button
            key={h}
            type="button"
            className={storage.retention_hours === h ? "active" : ""}
            disabled={retention.isPending || !can("system.view")}
            onClick={() => retention.mutate(h)}
          >
            {h === 0 ? t("admin.storage.retention_off") : t("admin.storage.retention_hours", { hours: h })}
          </button>
        ))}
      </div>

      <p className="drawer-section">{t("admin.storage.cleanup")}</p>
      <div className="storage-options">
        <label>
          <input
            type="checkbox"
            checked={options.intermediates}
            onChange={(e) => {
              setOptions({ ...options, intermediates: e.target.checked });
              setPreview(null);
            }}
          />
          <span>
            <strong>{t("admin.storage.opt_intermediates")}</strong>
            <small>{t("admin.storage.opt_intermediates_hint")}</small>
          </span>
        </label>
        <label>
          <input
            type="checkbox"
            checked={options.all_exports}
            onChange={(e) => {
              setOptions({ ...options, all_exports: e.target.checked });
              setPreview(null);
            }}
          />
          <span>
            <strong>{t("admin.storage.opt_all_exports")}</strong>
            <small>{t("admin.storage.opt_all_exports_hint")}</small>
          </span>
        </label>
      </div>

      <div className="storage-actions">
        <button type="button" className="btn secondary" onClick={showPreview}>
          {t("admin.storage.preview")}
        </button>
        {preview && preview.length > 0 && canClean && (
          <button
            type="button"
            className="btn danger"
            disabled={cleanup.isPending}
            onClick={() => cleanup.mutate()}
          >
            <IconTrash />
            {t("admin.storage.delete_now", { size: formatBytes(previewBytes) })}
          </button>
        )}
      </div>

      {done && <p className="storage-done">{done}</p>}

      {preview && (
        <div className="storage-preview">
          {preview.length === 0 ? (
            <p className="muted">{t("admin.storage.nothing_to_delete")}</p>
          ) : (
            <>
              <p className="muted">
                {t("admin.storage.will_delete", {
                  count: preview.length,
                  size: formatBytes(previewBytes),
                })}
              </p>
              <div className="quality-table-wrap">
                <table className="quality-table">
                  <thead>
                    <tr>
                      <th>{t("admin.storage.file")}</th>
                      <th>{t("admin.storage.why")}</th>
                      <th className="num">{t("admin.storage.age")}</th>
                      <th className="num">{t("admin.storage.size")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.map((p) => (
                      <tr key={p.path}>
                        <td className="mono wrap">{p.path}</td>
                        <td>{t(`admin.storage.reason.${p.reason}`)}</td>
                        <td className="num">
                          {t("admin.storage.hours", {
                            hours: Math.round(p.age_hours).toLocaleString(i18n.language),
                          })}
                        </td>
                        <td className="num">{formatBytes(p.bytes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </AdminPanel>
  );
}
