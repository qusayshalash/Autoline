import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Backup } from "../../../api/admin";
import {
  deleteBackup,
  fetchBackupSummary,
  fetchBackups,
  setBackupSchedule,
  startBackup,
} from "../../../api/admin";
import { apiErrorMessage, cancelJob, getJob } from "../../../api/client";
import { useAuth } from "../../../auth/AuthContext";
import { IconArchive, IconTrash } from "../../../components/admin/AdminIcons";
import { formatBytes } from "../../../components/admin/AdminUI";
import {
  Choice,
  ConfirmDialog,
  EmptyState,
  Notice,
  PathValue,
  SettingRow,
  SettingsCard,
  StatusBadge,
  Working,
} from "../../../components/admin/SettingsKit";
import { useToast } from "../../../components/admin/Toaster";
import ErrorBanner from "../../../components/ErrorBanner";
import QueryState from "../../../components/QueryState";

const POLL_MS = 700;

/** Off, daily, every other day, weekly. Hours because that is what the API stores. */
const SCHEDULE_CHOICES = [0, 24, 48, 168];
const SCHEDULE_LABELS: Record<number, string> = {
  0: "admin.backup.schedule_off",
  24: "admin.backup.schedule_daily",
  48: "admin.backup.schedule_2days",
  168: "admin.backup.schedule_weekly",
};

/**
 * Backups.
 *
 * Built around one distinction: a backup that has been read back, and one that has
 * merely been written. Only the first is called verified, and the count in the header is
 * of those - a row of green ticks for files nobody has opened is the failure this whole
 * feature exists to avoid. The same honesty applies to where the copies live: when they
 * sit on the disk they are protecting, the screen says so.
 */
export default function BackupsSection() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [includeOriginals, setIncludeOriginals] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Backup | null>(null);
  const timer = useRef<number | null>(null);

  const {
    data: summary,
    isLoading,
    isError: summaryFailed,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery({ queryKey: ["admin-backup-summary"], queryFn: fetchBackupSummary });
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
      setJobId(job.id);
      timer.current = window.setInterval(async () => {
        try {
          const state = await getJob(job.id);
          setProgress(
            state.status === "cancelling"
              ? t("admin.backup.cancelling")
              : describe(state.progress, t)
          );
          if (state.status === "done" || state.status === "error" || state.status === "cancelled") {
            if (timer.current) window.clearInterval(timer.current);
            timer.current = null;
            setProgress(null);
            setJobId(null);
            if (state.status === "error") {
              setError(state.error_message || t("admin.backup.failed"));
              toast("error", state.error_message || t("admin.backup.failed"));
            } else if (state.status === "done") {
              toast("success", t("settings.backups.done"));
            } else {
              toast("info", t("settings.backups.cancelled"));
            }
            refresh();
          }
        } catch (e) {
          if (timer.current) window.clearInterval(timer.current);
          timer.current = null;
          setProgress(null);
          setJobId(null);
          setError(apiErrorMessage(e, t("common.error_generic")));
        }
      }, POLL_MS);
    },
    onError: (e) => {
      setProgress(null);
      setError(apiErrorMessage(e, t("common.error_generic")));
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelJob(jobId!),
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const schedule = useMutation({
    mutationFn: setBackupSchedule,
    onSuccess: (_r, hours) => {
      refresh();
      toast(
        "success",
        hours === 0
          ? t("settings.backups.schedule_off_saved")
          : t("settings.backups.schedule_saved", { label: t(SCHEDULE_LABELS[hours]) })
      );
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const remove = useMutation({
    mutationFn: deleteBackup,
    onSuccess: () => {
      setPendingDelete(null);
      refresh();
      toast("success", t("settings.backups.deleted"));
    },
    onError: (e) => {
      setPendingDelete(null);
      setError(apiErrorMessage(e, t("common.error_generic")));
    },
  });

  if (isLoading || summaryFailed || !summary) {
    return (
      <QueryState
        loading={isLoading}
        error={summaryFailed ? summaryError : null}
        onRetry={refetchSummary}
      />
    );
  }

  const busy = run.isPending || progress !== null;
  const mayManage = can("system.manage");

  return (
    <>
      <SettingsCard
        icon={<IconArchive />}
        title={t("admin.backup.title")}
        description={t("settings.backups.desc")}
        actions={
          summary.verified_count > 0 ? (
            <StatusBadge tone={summary.stale ? "warning" : "healthy"}>
              {t("admin.backup.verified_count", { count: summary.verified_count })}
            </StatusBadge>
          ) : (
            <StatusBadge tone="warning">{t("admin.backup.none_yet")}</StatusBadge>
          )
        }
      >
        <ErrorBanner message={error} />

        {(summary.stale || summary.same_disk_as_data) && (
          <div className="set-notices">
            {summary.stale && (
              <Notice tone="warning">
                {summary.hours_since_last === null
                  ? t("admin.backup.stale_never")
                  : t("admin.backup.stale_since", {
                      hours: Math.round(summary.hours_since_last),
                    })}
              </Notice>
            )}
            {summary.same_disk_as_data && (
              <Notice tone="warning">{t("admin.backup.same_disk_warning")}</Notice>
            )}
          </div>
        )}

        {/* The four figures as a row of facts rather than four full-width rows: they are
            short, unrelated to each other, and read faster side by side. The path stays
            a row of its own because it is long and must not be squeezed. */}
        <dl className="set-facts">
          <div className="set-fact">
            <dt>{t("admin.backup.latest")}</dt>
            <dd>
              {summary.latest_at
                ? new Date(summary.latest_at).toLocaleDateString(i18n.language)
                : t("admin.backup.never")}
            </dd>
          </div>
          <div className="set-fact">
            <dt>{t("admin.backup.occupied")}</dt>
            <dd>{formatBytes(summary.total_bytes)}</dd>
          </div>
          <div className="set-fact">
            <dt>{t("admin.backup.keep")}</dt>
            <dd>{t("admin.backup.keep_value", { count: summary.keep })}</dd>
          </div>
          <div className="set-fact">
            <dt>{t("admin.storage.disk_free")}</dt>
            <dd>{formatBytes(summary.disk_free_bytes)}</dd>
          </div>
        </dl>

        <dl className="set-kv" style={{ marginTop: 14 }}>
          <div>
            <dt>{t("admin.backup.destination")}</dt>
            <dd>
              <PathValue>{summary.backup_dir}</PathValue>
            </dd>
          </div>
        </dl>
      </SettingsCard>

      <SettingsCard
        icon={<IconArchive />}
        title={t("settings.backups.run_title")}
        description={t("settings.backups.run_desc")}
        bodyless
      >
        <SettingRow
          title={t("admin.backup.schedule")}
          description={t("settings.backups.schedule_short")}
          hint={t("admin.backup.schedule_hint")}
          control={
            <Choice
              value={summary.interval_hours}
              disabled={schedule.isPending || !mayManage}
              ariaLabel={t("admin.backup.schedule")}
              onChange={(h) => schedule.mutate(h)}
              options={SCHEDULE_CHOICES.map((h) => ({ value: h, label: t(SCHEDULE_LABELS[h]) }))}
            />
          }
        />

        <SettingRow
          title={t("admin.backup.opt_originals")}
          description={t("admin.backup.opt_originals_hint")}
          control={
            <label className="set-check">
              <input
                type="checkbox"
                checked={includeOriginals}
                disabled={busy}
                onChange={(e) => setIncludeOriginals(e.target.checked)}
              />
              <span className="set-check-text" />
            </label>
          }
        />

        <SettingRow
          title={t("admin.backup.run_now")}
          description={t("admin.backup.how_it_works")}
          control={
            <>
              {progress && <Working label={progress} />}
              {jobId ? (
                <button
                  type="button"
                  className="set-btn secondary"
                  disabled={cancel.isPending}
                  onClick={() => cancel.mutate()}
                >
                  {t("common.cancel")}
                </button>
              ) : (
                <button
                  type="button"
                  className="set-btn primary"
                  disabled={busy || !mayManage}
                  onClick={() => run.mutate()}
                >
                  {t("admin.backup.run_now")}
                </button>
              )}
            </>
          }
        />
      </SettingsCard>

      <SettingsCard
        icon={<IconArchive />}
        title={t("settings.backups.history_title")}
        description={t("settings.backups.history_desc")}
        bodyless
      >
        {!backups || backups.length === 0 ? (
          <EmptyState
            icon={<IconArchive />}
            title={t("admin.backup.none_yet")}
            description={t("settings.backups.empty_desc")}
          />
        ) : (
          <div className="set-table-wrap">
            <table className="set-table">
              <thead>
                <tr>
                  <th>{t("admin.backup.taken_at")}</th>
                  <th>{t("admin.backup.state")}</th>
                  <th className="num">{t("admin.backup.contents")}</th>
                  <th className="num">{t("admin.storage.size")}</th>
                  <th className="shrink" />
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <BackupRow
                    key={b.name}
                    backup={b}
                    expanded={expanded === b.name}
                    onToggle={() => setExpanded(expanded === b.name ? null : b.name)}
                    onDelete={mayManage ? () => setPendingDelete(b) : undefined}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SettingsCard>

      <ConfirmDialog
        open={pendingDelete !== null}
        danger
        busy={remove.isPending}
        title={t("settings.backups.confirm_delete_title")}
        body={t("settings.backups.confirm_delete_body", {
          date: pendingDelete?.created_at
            ? new Date(pendingDelete.created_at).toLocaleString(i18n.language)
            : (pendingDelete?.name ?? ""),
        })}
        confirmLabel={t("common.delete")}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete.name)}
      />
    </>
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
          <button type="button" className="set-table-linkish" onClick={onToggle}>
            {backup.created_at
              ? new Date(backup.created_at).toLocaleString(i18n.language)
              : backup.name}
          </button>
        </td>
        <td>
          <StatusBadge tone={backup.intact ? "healthy" : "critical"} plain>
            {backup.intact ? t("admin.backup.verified") : t("admin.backup.unverified")}
          </StatusBadge>
        </td>
        <td className="num">
          {t("admin.backup.rows_and_files", {
            rows: rows.toLocaleString(i18n.language),
            files: backup.items.length,
          })}
        </td>
        <td className="num">{formatBytes(backup.bytes_on_disk)}</td>
        <td className="shrink">
          {onDelete && (
            <button
              type="button"
              className="set-btn ghost"
              onClick={onDelete}
              aria-label={t("common.delete") ?? ""}
              title={t("common.delete") ?? ""}
            >
              <IconTrash />
            </button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="detail">
          <td colSpan={5}>
            {backup.errors.length > 0 && (
              <ul className="set-detail-errors">
                {backup.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
            <ul className="set-detail-list">
              {backup.items.map((item) => (
                <li key={item.file}>
                  <span className="set-path">
                    <bdi>{item.file}</bdi>
                  </span>
                  <span style={{ color: "var(--text-muted)" }}>
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
