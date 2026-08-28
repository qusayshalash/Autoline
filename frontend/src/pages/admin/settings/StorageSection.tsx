import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { CompactionResult, StorageCandidate } from "../../../api/admin";
import {
  fetchCleanupPlan,
  fetchCompactionEstimate,
  fetchStorage,
  runCleanup,
  setRetention,
  startCompaction,
} from "../../../api/admin";
import { apiErrorMessage, cancelJob, getJob, listDatasets } from "../../../api/client";
import { useAuth } from "../../../auth/AuthContext";
import { IconDatabase, IconHardDrive } from "../../../components/admin/AdminIcons";
import { formatBytes } from "../../../components/admin/AdminUI";
import {
  Choice,
  ConfirmDialog,
  Notice,
  PathValue,
  SettingRow,
  SettingsCard,
  Working,
} from "../../../components/admin/SettingsKit";
import { useToast } from "../../../components/admin/Toaster";
import ErrorBanner from "../../../components/ErrorBanner";
import QueryState from "../../../components/QueryState";

const RETENTION_CHOICES = [0, 24, 72, 168, 720];
const POLL_MS = 800;

/** The five keys the storage service reports, in a fixed order so the stacked bar does
 *  not reshuffle as sizes change, and each keeps its colour between bar and legend.
 *
 *  The colours encode the one distinction that matters here: warm means the category can
 *  be deleted, cool means it never is. */
const CATEGORY_ORDER = ["datasets", "originals", "intermediates", "exports", "catalog"];
const CATEGORY_CLASS: Record<string, string> = {
  datasets: "db",
  originals: "originals",
  intermediates: "intermediates",
  exports: "exports",
  catalog: "catalog",
};

function categoryClass(key: string): string {
  return CATEGORY_CLASS[key] ?? "other";
}

/**
 * Storage, and the two things that change how much of it is used: what expires on its
 * own, and what a rewrite of a dataset file would give back.
 *
 * Nothing here deletes until the exact list has been fetched and shown - the server
 * answers "what would go" and "go" through separate endpoints for exactly that reason,
 * and the confirmation names the real figure rather than a guess.
 */
export default function StorageSection() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [options, setOptions] = useState({
    expired_exports: true,
    all_exports: false,
    intermediates: true,
  });
  const [preview, setPreview] = useState<StorageCandidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const {
    data: storage,
    isLoading,
    isError: loadFailed,
    error: loadError,
    refetch,
  } = useQuery({ queryKey: ["admin-storage"], queryFn: fetchStorage });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-storage"] });
    queryClient.invalidateQueries({ queryKey: ["admin-system"] });
  };

  const retention = useMutation({
    mutationFn: setRetention,
    onSuccess: (_r, hours) => {
      setError(null);
      refresh();
      toast(
        "success",
        hours === 0
          ? t("settings.storage.retention_saved_off")
          : t("settings.storage.retention_saved", { hours })
      );
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const cleanup = useMutation({
    mutationFn: () => runCleanup(options),
    onSuccess: (r) => {
      setPreview(null);
      setConfirming(false);
      refresh();
      toast(
        "success",
        t("admin.storage.cleaned", { count: r.removed_files, size: formatBytes(r.freed_bytes) })
      );
    },
    onError: (e) => {
      setConfirming(false);
      setError(apiErrorMessage(e, t("common.error_generic")));
    },
  });

  async function showPreview() {
    setError(null);
    try {
      setPreview(await fetchCleanupPlan(options));
    } catch (e) {
      setError(apiErrorMessage(e, t("common.error_generic")));
    }
  }

  if (isLoading || loadFailed || !storage) {
    return (
      <QueryState loading={isLoading} error={loadFailed ? loadError : null} onRetry={refetch} />
    );
  }

  const mayManage = can("system.manage");
  const previewBytes = preview?.reduce((a, p) => a + p.bytes, 0) ?? 0;
  const shown = [...storage.categories]
    .filter((c) => c.bytes > 0)
    .sort((a, b) => CATEGORY_ORDER.indexOf(a.key) - CATEGORY_ORDER.indexOf(b.key));
  const total = Math.max(1, storage.total_bytes);

  return (
    <>
      <SettingsCard
        icon={<IconHardDrive />}
        title={t("settings.storage.title")}
        description={t("settings.storage.desc")}
      >
        <ErrorBanner message={error} />

        <div className="set-storage-total">
          <strong>{formatBytes(storage.total_bytes)}</strong>
          <span>{t("settings.storage.free", { size: formatBytes(storage.disk_free_bytes) })}</span>
        </div>

        <div
          className="set-stack"
          role="img"
          aria-label={t("settings.storage.title")}
        >
          {shown.map((c) => (
            <i
              key={c.key}
              className={categoryClass(c.key)}
              style={{ width: `${(c.bytes / total) * 100}%` }}
            />
          ))}
        </div>

        <div className="set-legend">
          {shown.map((c) => (
            <div key={c.key} className="set-legend-row">
              <span className="set-legend-key">
                <i className={categoryClass(c.key)} />
                {t(`admin.storage.category.${c.key}`)}
                {!c.removable && (
                  <em className="set-legend-lock">{t("admin.storage.protected")}</em>
                )}
              </span>
              <span className="set-legend-size">{formatBytes(c.bytes)}</span>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 18 }}>
          <dl className="set-kv">
            <div>
              <dt>{t("admin.storage.reclaimable")}</dt>
              <dd>
                {formatBytes(storage.reclaimable_bytes)}
                {storage.reclaimable_files > 0 &&
                  ` · ${storage.reclaimable_files.toLocaleString(i18n.language)}`}
              </dd>
            </div>
            <div>
              <dt>{t("admin.storage.data_dir")}</dt>
              <dd>
                <PathValue>{storage.data_dir}</PathValue>
              </dd>
            </div>
          </dl>
        </div>
      </SettingsCard>

      <SettingsCard
        icon={<IconDatabase />}
        title={t("settings.storage.reclaim_title")}
        description={t("settings.storage.reclaim_desc")}
        bodyless
      >
        <SettingRow
          title={t("admin.storage.retention")}
          description={t("settings.storage.retention_short")}
          hint={t("admin.storage.retention_hint")}
          control={
            <Choice
              value={storage.retention_hours}
              disabled={retention.isPending || !mayManage}
              ariaLabel={t("admin.storage.retention")}
              onChange={(h) => retention.mutate(h)}
              options={RETENTION_CHOICES.map((h) => ({
                value: h,
                label:
                  h === 0
                    ? t("admin.storage.retention_off")
                    : t("admin.storage.retention_hours", { hours: h }),
              }))}
            />
          }
        />

        <SettingRow
          title={t("admin.storage.cleanup")}
          description={t("settings.storage.cleanup_short")}
          stacked
        >
          <div className="set-checks" style={{ marginTop: 12 }}>
            <label className="set-check">
              <input
                type="checkbox"
                checked={options.intermediates}
                onChange={(e) => {
                  setOptions({ ...options, intermediates: e.target.checked });
                  setPreview(null);
                }}
              />
              <span className="set-check-text">
                <strong>{t("admin.storage.opt_intermediates")}</strong>
                <small>{t("admin.storage.opt_intermediates_hint")}</small>
              </span>
            </label>
            <label className="set-check">
              <input
                type="checkbox"
                checked={options.all_exports}
                onChange={(e) => {
                  setOptions({ ...options, all_exports: e.target.checked });
                  setPreview(null);
                }}
              />
              <span className="set-check-text">
                <strong>{t("admin.storage.opt_all_exports")}</strong>
                <small>{t("admin.storage.opt_all_exports_hint")}</small>
              </span>
            </label>
          </div>

          <div className="set-actions" style={{ marginTop: 16 }}>
            <button type="button" className="set-btn secondary" onClick={showPreview}>
              {t("admin.storage.preview")}
            </button>
            {preview && preview.length > 0 && mayManage && (
              <button
                type="button"
                className="set-btn danger"
                disabled={cleanup.isPending}
                onClick={() => setConfirming(true)}
              >
                {t("admin.storage.delete_now", { size: formatBytes(previewBytes) })}
              </button>
            )}
          </div>

          {preview && (
            <div style={{ marginTop: 14 }}>
              {preview.length === 0 ? (
                <Notice>{t("admin.storage.nothing_to_delete")}</Notice>
              ) : (
                <>
                  <Notice tone="warning">
                    {t("admin.storage.will_delete", {
                      count: preview.length,
                      size: formatBytes(previewBytes),
                    })}
                  </Notice>
                  <div className="set-table-wrap" style={{ marginTop: 12, borderTop: 0 }}>
                    <table className="set-table">
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
                            <td>
                              <span className="set-path">
                                <bdi>{p.path}</bdi>
                              </span>
                            </td>
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
        </SettingRow>
      </SettingsCard>

      <CompactionCard />

      <ConfirmDialog
        open={confirming}
        danger
        busy={cleanup.isPending}
        title={t("settings.storage.confirm_cleanup_title")}
        body={t("settings.storage.confirm_cleanup_body", {
          count: preview?.length ?? 0,
          size: formatBytes(previewBytes),
        })}
        confirmLabel={t("settings.storage.confirm_cleanup_ok")}
        onCancel={() => setConfirming(false)}
        onConfirm={() => cleanup.mutate()}
      />
    </>
  );
}

/* --- database compaction ---------------------------------------------------- */

/**
 * Rewriting a dataset file without its free space.
 *
 * Per file rather than one "compact everything": each run rewrites gigabytes and briefly
 * holds that file's write lock, so one at a time is both the honest presentation and the
 * safe one.
 */
function CompactionCard() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [error, setError] = useState<string | null>(null);

  const { data: files } = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
  const ready = (files ?? []).filter((f) => f.status === "ready");

  if (!can("system.manage") || ready.length === 0) return null;

  return (
    <SettingsCard
      icon={<IconDatabase />}
      title={t("admin.compaction.title")}
      description={t("settings.compaction.desc")}
      bodyless
    >
      {error && (
        <div style={{ padding: "0 22px" }}>
          <ErrorBanner message={error} />
        </div>
      )}
      {ready.map((f) => (
        <CompactionRow key={f.id} datasetId={f.id} name={f.original_filename} onError={setError} />
      ))}
    </SettingsCard>
  );
}

function CompactionRow({
  datasetId,
  name,
  onError,
}: {
  datasetId: string;
  name: string;
  onError: (m: string | null) => void;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const [progress, setProgress] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const timer = useRef<number | null>(null);

  const { data: estimate, refetch } = useQuery({
    queryKey: ["compaction-estimate", datasetId],
    queryFn: () => fetchCompactionEstimate(datasetId),
  });

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
  }, []);

  async function run() {
    onError(null);
    setConfirming(false);
    setCancelling(false);
    setProgress(t("admin.compaction.running"));
    try {
      const job = await startCompaction(datasetId);
      setJobId(job.id);
      timer.current = window.setInterval(async () => {
        try {
          const state = await getJob(job.id);
          setProgress(
            state.status === "cancelling"
              ? t("admin.compaction.cancelling")
              : describe(state.progress, t)
          );
          if (state.status === "done" || state.status === "error" || state.status === "cancelled") {
            if (timer.current) window.clearInterval(timer.current);
            timer.current = null;
            setProgress(null);
            setJobId(null);
            setCancelling(false);
            if (state.status === "error") {
              onError(state.error_message || t("admin.compaction.failed"));
              toast("error", state.error_message || t("admin.compaction.failed"));
            } else if (state.status === "done") {
              const r = state.result as unknown as CompactionResult;
              refetch();
              toast(
                "success",
                r?.skipped
                  ? t("admin.compaction.already_compact")
                  : t("admin.compaction.freed", {
                      size: formatBytes(r?.freed_bytes ?? 0),
                      before: formatBytes(r?.bytes_before ?? 0),
                      after: formatBytes(r?.bytes_after ?? 0),
                    })
              );
            } else {
              toast("info", t("settings.compaction.cancelled"));
            }
          }
        } catch (e) {
          if (timer.current) window.clearInterval(timer.current);
          timer.current = null;
          setProgress(null);
          setJobId(null);
          onError(apiErrorMessage(e, t("common.error_generic")));
        }
      }, POLL_MS);
    } catch (e) {
      setProgress(null);
      onError(apiErrorMessage(e, t("common.error_generic")));
    }
  }

  async function cancel() {
    if (!jobId) return;
    setCancelling(true);
    try {
      await cancelJob(jobId);
    } catch (e) {
      setCancelling(false);
      onError(apiErrorMessage(e, t("common.error_generic")));
    }
  }

  return (
    <>
      <SettingRow
        title={name}
        description={
          estimate ? t("settings.compaction.size", { size: formatBytes(estimate.file_bytes) }) : "—"
        }
        control={
          progress ? (
            <>
              <Working label={progress} />
              {jobId && (
                <button
                  type="button"
                  className="set-btn secondary small"
                  disabled={cancelling}
                  onClick={cancel}
                >
                  {t("common.cancel")}
                </button>
              )}
            </>
          ) : (
            <button
              type="button"
              className="set-btn secondary"
              onClick={() => setConfirming(true)}
            >
              {t("admin.compaction.run")}
            </button>
          )
        }
      />
      <ConfirmDialog
        open={confirming}
        title={t("settings.compaction.confirm_title")}
        body={t("settings.compaction.confirm_body")}
        confirmLabel={t("settings.compaction.confirm_ok")}
        onCancel={() => setConfirming(false)}
        onConfirm={run}
      />
    </>
  );
}

type Translate = ReturnType<typeof useTranslation>["t"];

/** Job progress is a machine word; this is what it means on screen. */
function describe(progress: string, t: Translate): string {
  const known = ["writing", "verifying", "swapping"];
  return known.includes(progress)
    ? t(`admin.compaction.progress_${progress}`)
    : t("admin.compaction.running");
}
