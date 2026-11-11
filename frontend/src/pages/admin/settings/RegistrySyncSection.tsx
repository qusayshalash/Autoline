import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import {
  discardRegistryPreview,
  fetchRegistrySync,
  setRegistrySync,
  startRegistryApply,
  startRegistryPreview,
  type RegistryPreview,
} from "../../../api/admin";
import { apiErrorMessage, getJob, listDatasets } from "../../../api/client";
import { useAuth } from "../../../auth/AuthContext";
import { IconRefresh } from "../../../components/admin/AdminIcons";
import {
  Choice,
  Notice,
  SettingRow,
  SettingsCard,
  StatusBadge,
  Working,
} from "../../../components/admin/SettingsKit";
import { useToast } from "../../../components/admin/Toaster";
import { useConfirm } from "../../../components/ConfirmProvider";
import ErrorBanner from "../../../components/ErrorBanner";
import QueryState from "../../../components/QueryState";
import { columnLabel } from "../../../data/columnDictionary";
import { formatDateTime } from "../../../data/datetime";
import { DICTIONARY_COLUMNS, translateValue } from "../../../data/valueDictionary";

const TERMINAL = new Set(["done", "error", "cancelled"]);

/**
 * Keeping the vehicle file in step with the Ministry of Transport's registry.
 *
 * Two buttons, never one: a preview that only reads and reports, and an apply that only
 * acts on what the preview found. The numbers are shown before anything changes, because
 * a sync that rewrites millions of rows should never be something one discovers after.
 */
export default function RegistrySyncSection() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { can } = useAuth();
  const mayManage = can("system.manage");
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<boolean | null>(null);
  const n = (v: number) => v.toLocaleString(lang);

  const status = useQuery({
    queryKey: ["registry-sync"],
    queryFn: fetchRegistrySync,
    // while a run is going and this tab did not start it, keep asking until it ends
    refetchInterval: (q) => (q.state.data?.running && !jobId ? 4000 : false),
  });
  const { data: datasets } = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });

  const { data: job } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => (TERMINAL.has(q.state.data?.status ?? "") ? false : 1500),
    refetchIntervalInBackground: true,
  });

  useEffect(() => {
    if (!job || !TERMINAL.has(job.status)) return;
    setJobId(null);
    qc.invalidateQueries({ queryKey: ["registry-sync"] });
    if (job.status === "done") {
      toast("success", job.kind === "registry_apply" ? t("registry.applied") : t("registry.previewed"));
      if (job.kind === "registry_apply") {
        qc.invalidateQueries({ queryKey: ["data"] });
        qc.invalidateQueries({ queryKey: ["datasets"] });
      }
    } else if (job.status === "error") {
      setError(
        t(`errors.${job.error_message}`, {
          defaultValue: job.error_message || t("common.error_generic"),
        })
      );
    }
  }, [job, qc, t, toast]);

  const onError = (e: unknown) => setError(apiErrorMessage(e, t("common.error_generic")));

  const config = useMutation({
    mutationFn: setRegistrySync,
    onSuccess: (data) => {
      qc.setQueryData(["registry-sync"], data);
      setError(null);
      toast("success", t("settings.maintenance.saved"));
    },
    onError,
  });
  const preview = useMutation({
    mutationFn: startRegistryPreview,
    onSuccess: (j) => {
      setError(null);
      setJobId(j.id);
    },
    onError,
  });
  const apply = useMutation({
    mutationFn: (asBaseline: boolean) => startRegistryApply(asBaseline),
    onSuccess: (j) => {
      setError(null);
      setJobId(j.id);
    },
    onError,
  });
  const discard = useMutation({
    mutationFn: discardRegistryPreview,
    onSuccess: (data) => qc.setQueryData(["registry-sync"], data),
    onError,
  });

  if (status.isLoading || status.isError || !status.data) {
    return (
      <QueryState
        loading={status.isLoading}
        error={status.isError ? status.error : null}
        onRetry={status.refetch}
      />
    );
  }
  const s = status.data;
  const busy = s.running || !!jobId;
  const keyed = (datasets ?? []).filter((d) => d.status === "ready" && d.key_columns?.length);
  const firstSync = !s.last_report;
  const asBaseline = baseline ?? firstSync;
  // only the columns the dictionary translates: a new model name is not a gap in it
  const newValues = (s.preview?.new_values ?? []).filter((v) => DICTIONARY_COLUMNS.has(v.column));

  async function onApply(p: RegistryPreview) {
    const body = t("registry.confirm_apply", {
      new: n(p.new),
      changed: n(p.changed),
      removed: n(p.removed),
    });
    if (await confirm({ body, confirmLabel: t("registry.apply"), danger: false })) {
      apply.mutate(asBaseline);
    }
  }

  const badge = busy ? (
    <StatusBadge tone="neutral">{t("registry.badge_running")}</StatusBadge>
  ) : s.preview ? (
    <StatusBadge tone="warning">{t("registry.badge_preview")}</StatusBadge>
  ) : s.last_report ? (
    <StatusBadge tone="healthy">{t("registry.badge_synced")}</StatusBadge>
  ) : (
    <StatusBadge tone="neutral">{t("registry.badge_never")}</StatusBadge>
  );

  return (
    <SettingsCard
      icon={<IconRefresh />}
      title={t("registry.title")}
      description={t("registry.desc")}
      actions={badge}
      bodyless
    >
      {error && (
        <div style={{ padding: "0 22px" }}>
          <ErrorBanner message={error} />
        </div>
      )}

      <SettingRow
        title={t("registry.dataset")}
        description={s.dataset_name ?? t("registry.dataset_none")}
        hint={t("registry.dataset_hint")}
        control={
          <Choice<string>
            value={s.dataset_id ?? ""}
            disabled={!mayManage || busy || config.isPending}
            ariaLabel={t("registry.dataset")}
            onChange={(id) =>
              config.mutate({ dataset_id: id || null, schedule: id ? s.schedule : "off" })
            }
            options={[
              { value: "", label: t("registry.dataset_none") },
              ...keyed.map((d) => ({ value: d.id, label: d.original_filename })),
            ]}
          />
        }
      />

      <SettingRow
        title={t("registry.schedule")}
        description={
          s.schedule === "daily" ? t("registry.schedule_daily_desc") : t("registry.schedule_off_desc")
        }
        hint={t("registry.schedule_hint")}
        control={
          <Choice<"off" | "daily">
            value={s.schedule}
            disabled={!mayManage || !s.dataset_id || busy || config.isPending}
            ariaLabel={t("registry.schedule")}
            onChange={(schedule) => config.mutate({ dataset_id: s.dataset_id, schedule })}
            options={[
              { value: "off", label: t("registry.schedule_off") },
              { value: "daily", label: t("registry.schedule_daily") },
            ]}
          />
        }
      />

      <SettingRow
        title={t("registry.now")}
        description={t("registry.now_desc")}
        control={
          busy ? (
            <Working label={progressLabel(job?.progress, t)} />
          ) : (
            <button
              type="button"
              className="set-btn primary"
              disabled={!mayManage || !s.dataset_id || preview.isPending}
              onClick={() => preview.mutate()}
            >
              {t("registry.preview")}
            </button>
          )
        }
      />

      {s.preview && !busy && (
        <div className="registry-preview">
          <div className="registry-preview-head">
            <strong>{t("registry.preview_title")}</strong>
            <span>
              {t("registry.preview_meta", {
                when: formatDateTime(s.preview.created_at, lang),
                total: n(s.preview.source_rows),
              })}
            </span>
          </div>

          <div className="registry-numbers">
            <Figure tone="new" label={t("registry.new")} value={n(s.preview.new)} />
            <Figure tone="changed" label={t("registry.changed")} value={n(s.preview.changed)} />
            <Figure tone="removed" label={t("registry.removed")} value={n(s.preview.removed)} />
            <Figure tone="returned" label={t("registry.returned")} value={n(s.preview.returned)} />
          </div>

          {s.preview.changed_columns.length > 0 && (
            <div className="registry-block">
              <h3>{t("registry.what_changed")}</h3>
              <ul className="registry-bars">
                {s.preview.changed_columns.map((c) => (
                  <li key={c.column}>
                    <span className="registry-bar-label">{columnLabel(c.column, lang)}</span>
                    <span className="registry-bar-track">
                      <span
                        className="registry-bar-fill"
                        style={{
                          width: `${Math.max(2, (c.count / Math.max(1, s.preview!.changed)) * 100)}%`,
                        }}
                      />
                    </span>
                    <span className="registry-bar-value">{n(c.count)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {newValues.length > 0 && (
            <div className="registry-block">
              <h3>{t("registry.new_values")}</h3>
              <p className="registry-note">{t("registry.new_values_hint")}</p>
              <ul className="registry-values">
                {newValues.map((v) => {
                  const shown = translateValue(v.value, lang);
                  const untranslated = shown === v.value && !lang.startsWith("he");
                  return (
                    <li key={`${v.column}|${v.value}`} className={untranslated ? "untranslated" : ""}>
                      <span className="registry-value-col">{columnLabel(v.column, lang)}</span>
                      <bdi className="registry-value" dir="rtl">{v.value}</bdi>
                      {!untranslated && <span className="registry-value-tr">{shown}</span>}
                      {untranslated && (
                        <span className="registry-value-flag">{t("registry.untranslated")}</span>
                      )}
                      <span className="registry-value-count">{n(v.count)}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {firstSync && (
            <Notice tone="warning">{t("registry.first_sync_notice")}</Notice>
          )}

          <div className="registry-actions">
            <label className="registry-check">
              <input
                type="checkbox"
                checked={asBaseline}
                disabled={!mayManage}
                onChange={(e) => setBaseline(e.target.checked)}
              />
              <span>
                {t("registry.baseline")}
                <small>{t("registry.baseline_hint")}</small>
              </span>
            </label>
            <div className="registry-buttons">
              <button
                type="button"
                className="set-btn secondary"
                disabled={!mayManage || discard.isPending}
                onClick={() => discard.mutate()}
              >
                {t("registry.discard")}
              </button>
              <button
                type="button"
                className="set-btn primary"
                disabled={!mayManage || apply.isPending}
                onClick={() => onApply(s.preview!)}
              >
                {t("registry.apply")}
              </button>
            </div>
          </div>
        </div>
      )}

      {s.last_report && (
        <SettingRow
          title={t("registry.last")}
          description={t("registry.last_desc", {
            when: formatDateTime(s.last_report.applied_at, lang),
            new: n(s.last_report.new),
            changed: n(s.last_report.changed),
            removed: n(s.last_report.removed),
          })}
        >
          {s.last_report.baseline && (
            <p className="set-row-desc">{t("registry.last_baseline")}</p>
          )}
        </SettingRow>
      )}

      <div style={{ padding: "6px 22px 18px" }}>
        <a className="registry-source" href={s.source.page} target="_blank" rel="noreferrer">
          {t("registry.source_link")}
        </a>
      </div>
    </SettingsCard>
  );
}

function Figure({ tone, label, value }: { tone: string; label: string; value: string }) {
  return (
    <div className={`registry-figure ${tone}`}>
      <span className="registry-figure-value">{value}</span>
      <span className="registry-figure-label">{label}</span>
    </div>
  );
}

/** The job's progress line, said in the reader's language. */
function progressLabel(progress: string | undefined, t: TFunction): string {
  const fetching = /^fetching (\d+)\/(\d+)$/.exec(progress ?? "");
  if (fetching) return t("registry.step_fetching", { done: fetching[1], total: fetching[2] });
  switch (progress) {
    case "comparing":
      return t("registry.step_comparing");
    case "applying":
      return t("registry.step_applying");
    case "marking":
    case "replaying corrections":
    case "rebuilding the cleaned copy":
      return t("registry.step_finishing");
    default:
      return t("registry.step_starting");
  }
}
