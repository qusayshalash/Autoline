import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Backup } from "../../api/admin";
import {
  deleteBackup,
  fetchBackupSummary,
  fetchBackups,
  startBackup,
} from "../../api/admin";
import { apiErrorMessage, getJob } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconDatabase, IconTrash } from "../../components/admin/AdminIcons";
import { AdminPanel, formatBytes } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";
import LoadingState from "../../components/LoadingState";

const POLL_MS = 700;

/**
 * Backups.
 *
 * The screen is built around one distinction: a backup that has been read back, and one
 * that has merely been written. Only the first is called verified, and the count in the
 * header is of those - because a row of green ticks for files nobody has opened is the
 * failure this whole feature exists to avoid.
 *
 * The same honesty applies to where the copies live: when they sit on the disk they are
 * protecting, the panel says so rather than letting the word "backup" imply more.
 */
export default function BackupPanel() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();

  const [includeOriginals, setIncludeOriginals] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const { data: summary, isLoading } = useQuery({
    queryKey: ["admin-backup-summary"],
    queryFn: fetchBackupSummary,
  });
  const { data: backups } = useQuery({ queryKey: ["admin-backups"], queryFn: fetchBackups });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-backups"] });
    queryClient.invalidateQueries({ queryKey: ["admin-backup-summary"] });
    queryClient.invalidateQueries({ queryKey: ["admin-storage"] });
  };

  // the poll is cleared on unmount: navigating away mid-backup should stop the polling,
  // not the backup, which is running on the server and finishes either way
  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
  }, []);

  const run = useMutation({
    mutationFn: () => startBackup(includeOriginals),
    onMutate: () => {
      setError(null);
      setProgress(t("admin.backup.starting"));
    },
    onSuccess: (job) => {
      timer.current = window.setInterval(async () => {
        try {
          const state = await getJob(job.id);
          setProgress(describe(state.progress, t));
          if (state.status === "done" || state.status === "error") {
            if (timer.current) window.clearInterval(timer.current);
            timer.current = null;
            setProgress(null);
            if (state.status === "error") {
              setError(state.error_message || t("admin.backup.failed"));
            }
            refresh();
          }
        } catch (e) {
          if (timer.current) window.clearInterval(timer.current);
          timer.current = null;
          setProgress(null);
          setError(apiErrorMessage(e, t("common.error_generic")));
        }
      }, POLL_MS);
    },
    onError: (e) => {
      setProgress(null);
      setError(apiErrorMessage(e, t("common.error_generic")));
    },
  });

  const remove = useMutation({
    mutationFn: deleteBackup,
    onSuccess: refresh,
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  if (isLoading || !summary) return <LoadingState />;

  const busy = run.isPending || progress !== null;
  const canDelete = can("datasets.delete");

  return (
    <AdminPanel
      icon={<IconDatabase />}
      title={t("admin.backup.title")}
      note={
        summary.verified_count > 0
          ? t("admin.backup.verified_count", { count: summary.verified_count })
          : t("admin.backup.none_yet")
      }
    >
      <ErrorBanner message={error} />

      {summary.count === 0 && <p className="backup-warn">{t("admin.backup.no_backup_warning")}</p>}
      {summary.same_disk_as_data && (
        <p className="backup-warn">{t("admin.backup.same_disk_warning")}</p>
      )}

      <dl className="detail-list">
        <div>
          <dt>{t("admin.backup.latest")}</dt>
          <dd>
            {summary.latest_at
              ? new Date(summary.latest_at).toLocaleString(i18n.language)
              : t("admin.backup.never")}
          </dd>
        </div>
        <div>
          <dt>{t("admin.backup.occupied")}</dt>
          <dd>{formatBytes(summary.total_bytes)}</dd>
        </div>
        <div>
          <dt>{t("admin.backup.keep")}</dt>
          <dd>{t("admin.backup.keep_value", { count: summary.keep })}</dd>
        </div>
        <div>
          <dt>{t("admin.backup.destination")}</dt>
          <dd className="mono wrap">{summary.backup_dir}</dd>
        </div>
        <div>
          <dt>{t("admin.storage.disk_free")}</dt>
          <dd>{formatBytes(summary.disk_free_bytes)}</dd>
        </div>
      </dl>

      <p className="muted admin-note">{t("admin.backup.how_it_works")}</p>

      <div className="storage-options">
        <label>
          <input
            type="checkbox"
            checked={includeOriginals}
            disabled={busy}
            onChange={(e) => setIncludeOriginals(e.target.checked)}
          />
          <span>
            <strong>{t("admin.backup.opt_originals")}</strong>
            <small>{t("admin.backup.opt_originals_hint")}</small>
          </span>
        </label>
      </div>

      <div className="storage-actions">
        <button type="button" className="btn" disabled={busy} onClick={() => run.mutate()}>
          {busy ? t("admin.backup.running") : t("admin.backup.run_now")}
        </button>
        {progress && <span className="backup-progress">{progress}</span>}
      </div>

      {backups && backups.length > 0 && (
        <div className="quality-table-wrap">
          <table className="quality-table">
            <thead>
              <tr>
                <th>{t("admin.backup.taken_at")}</th>
                <th>{t("admin.backup.state")}</th>
                <th className="num">{t("admin.backup.contents")}</th>
                <th className="num">{t("admin.storage.size")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <BackupRow
                  key={b.name}
                  backup={b}
                  expanded={expanded === b.name}
                  onToggle={() => setExpanded(expanded === b.name ? null : b.name)}
                  onDelete={canDelete ? () => remove.mutate(b.name) : undefined}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AdminPanel>
  );
}

function BackupRow({
  backup,
  expanded,
  onToggle,
  onDelete,
}: {
  backup: Backup;
  expanded: boolean;
  onToggle: () => void;
  onDelete?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const rows = backup.items.reduce(
    (total, item) => total + Object.values(item.tables).reduce((a, n) => a + n, 0),
    0
  );

  return (
    <>
      <tr>
        <td>
          <button type="button" className="linkish" onClick={onToggle}>
            {backup.created_at
              ? new Date(backup.created_at).toLocaleString(i18n.language)
              : backup.name}
          </button>
        </td>
        <td>
          <span
            className={`status-pill ${backup.intact ? "status-active" : "status-suspended"}`}
          >
            {backup.intact ? t("admin.backup.verified") : t("admin.backup.unverified")}
          </span>
        </td>
        <td className="num">
          {t("admin.backup.rows_and_files", {
            rows: rows.toLocaleString(i18n.language),
            files: backup.items.length,
          })}
        </td>
        <td className="num">{formatBytes(backup.bytes_on_disk)}</td>
        <td className="num">
          {onDelete && (
            <button
              type="button"
              className="icon-btn"
              onClick={onDelete}
              aria-label={t("common.delete")}
            >
              <IconTrash />
            </button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="backup-detail">
          <td colSpan={5}>
            {backup.errors.length > 0 && (
              <ul className="backup-errors">
                {backup.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
            <ul className="backup-items">
              {backup.items.map((item) => (
                <li key={item.file}>
                  <span className="mono wrap">{item.file}</span>
                  <span className="muted">
                    {Object.entries(item.tables)
                      .map(([table, n]) => `${table}: ${n.toLocaleString(i18n.language)}`)
                      .join(" · ") || t(`admin.backup.kind.${item.kind}`)}
                  </span>
                  <span className="num">{formatBytes(item.bytes)}</span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}

/** The translator, typed as react-i18next hands it out rather than approximated. A
 *  hand-written `(k: string) => string` is close enough for the editor and not close
 *  enough for `tsc -b`, which is what the build actually runs. */
type Translate = ReturnType<typeof useTranslation>["t"];

/** Job progress arrives as a machine string like "dataset:2/5"; this is what it means. */
function describe(progress: string, t: Translate): string {
  if (!progress) return t("admin.backup.starting");
  if (progress.startsWith("dataset:")) {
    const [done, total] = progress.slice("dataset:".length).split("/");
    return t("admin.backup.progress_dataset", { done, total });
  }
  const known = ["catalog", "key", "originals", "done", "starting"];
  return known.includes(progress)
    ? t(`admin.backup.progress_${progress}`)
    : t("admin.backup.running");
}
