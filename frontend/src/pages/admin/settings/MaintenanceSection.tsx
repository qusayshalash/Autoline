import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchHousekeeping, setHousekeeping, sweepHousekeeping } from "../../../api/admin";
import { apiErrorMessage, setArrivalWindow } from "../../../api/client";
import { useAuth } from "../../../auth/AuthContext";
import { IconBroom } from "../../../components/admin/AdminIcons";
import {
  Choice,
  Notice,
  SettingRow,
  SettingsCard,
  StatusBadge,
} from "../../../components/admin/SettingsKit";
import { useToast } from "../../../components/admin/Toaster";
import ErrorBanner from "../../../components/ErrorBanner";
import QueryState from "../../../components/QueryState";

/** Offered periods, in days. 0 is off. */
const JOB_CHOICES = [0, 30, 90, 365];
const CLEANING_CHOICES = [0, 90, 365, 730];

/** How long a record from a new batch stays marked. Nothing longer than a month: past
 *  that the mark is no longer telling anyone anything they did not already know. */
const ARRIVAL_CHOICES = [1, 3, 7, 14, 30];
const DEFAULT_ARRIVAL_WINDOW = 7;

/**
 * The automatic sweep over the catalog's two append-only tables.
 *
 * A window onto something that already runs, not a switch that starts it. Both due
 * counts are normally zero, and that is the point: the rows go on a schedule, so what
 * this mostly reports is that there is nothing to report.
 *
 * The one figure worth understanding is the held count. An export's row is what tells
 * the download endpoint its file's format, so an old export whose file is still on disk
 * keeps its row past its date - it is not overdue, it is in use.
 */
export default function MaintenanceSection() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const [arrivalDays, setArrivalDays] = useState(DEFAULT_ARRIVAL_WINDOW);

  const {
    data,
    isLoading,
    isError,
    error: loadError,
    refetch,
  } = useQuery({
    queryKey: ["admin-housekeeping"],
    queryFn: fetchHousekeeping,
    enabled: can("system.view"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-housekeeping"] });
    queryClient.invalidateQueries({ queryKey: ["admin-overview"] });
  };

  const retention = useMutation({
    mutationFn: setHousekeeping,
    onSuccess: () => {
      refresh();
      toast("success", t("settings.maintenance.saved"));
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  // Not part of the housekeeping payload: it is one setting for every dataset rather
  // than a per-table retention, and it decides how long something is *shown*, not how
  // long it is kept.
  const arrivalWindow = useMutation({
    mutationFn: (days: number) => setArrivalWindow(days),
    onSuccess: () => toast("success", t("settings.maintenance.saved")),
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const sweep = useMutation({
    mutationFn: sweepHousekeeping,
    onSuccess: (r) => {
      const removed = r.jobs_removed + r.cleaning_removed;
      refresh();
      toast(
        "success",
        removed === 0
          ? t("admin.housekeeping.nothing_due")
          : t("admin.housekeeping.swept", { count: removed.toLocaleString(i18n.language) })
      );
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  if (isLoading || isError || !data) {
    return <QueryState loading={isLoading} error={isError ? loadError : null} onRetry={refetch} />;
  }

  const mayManage = can("system.manage");
  const n = (v: number) => v.toLocaleString(i18n.language);
  const label = (days: number) =>
    days === 0 ? t("admin.housekeeping.off") : t("admin.housekeeping.days", { count: days });
  const totalDue = data.jobs_due + data.cleaning_due;

  return (
    <SettingsCard
      icon={<IconBroom />}
      title={t("admin.housekeeping.title")}
      description={t("settings.maintenance.desc")}
      actions={
        <StatusBadge tone={totalDue > 0 ? "warning" : "healthy"}>
          {totalDue > 0
            ? t("settings.maintenance.due_badge", { count: n(totalDue) })
            : t("settings.maintenance.clean_badge")}
        </StatusBadge>
      }
      bodyless
    >
      {error && (
        <div style={{ padding: "0 22px" }}>
          <ErrorBanner message={error} />
        </div>
      )}

      <SettingRow
        title={t("admin.housekeeping.jobs")}
        description={t("admin.housekeeping.jobs_state", {
          total: n(data.jobs_total),
          due: n(data.jobs_due),
        })}
        hint={t("admin.housekeeping.jobs_hint")}
        control={
          <Choice
            value={data.jobs_retention_days}
            disabled={!mayManage || retention.isPending}
            ariaLabel={t("admin.housekeeping.jobs")}
            onChange={(days) => retention.mutate({ jobs_retention_days: days })}
            options={JOB_CHOICES.map((d) => ({ value: d, label: label(d) }))}
          />
        }
      >
        {data.jobs_held_by_exports > 0 && (
          <div style={{ marginTop: 12 }}>
            <Notice>{t("admin.housekeeping.held", { count: n(data.jobs_held_by_exports) })}</Notice>
          </div>
        )}
      </SettingRow>

      <SettingRow
        title={t("settings.arrivals.title")}
        description={t("settings.arrivals.desc")}
        hint={t("settings.arrivals.hint")}
        control={
          <Choice
            value={arrivalDays}
            disabled={!mayManage || arrivalWindow.isPending}
            ariaLabel={t("settings.arrivals.title")}
            onChange={(days) => {
              setArrivalDays(days);
              arrivalWindow.mutate(days);
            }}
            options={ARRIVAL_CHOICES.map((d) => ({
              value: d,
              label: t("arrivals.within", { count: d }),
            }))}
          />
        }
      />

      <SettingRow
        title={t("admin.housekeeping.cleaning")}
        description={t("admin.housekeeping.cleaning_state", {
          total: n(data.cleaning_total),
          due: n(data.cleaning_due),
        })}
        hint={t("admin.housekeeping.cleaning_hint")}
        control={
          <Choice
            value={data.cleaning_retention_days}
            disabled={!mayManage || retention.isPending}
            ariaLabel={t("admin.housekeeping.cleaning")}
            onChange={(days) => retention.mutate({ cleaning_retention_days: days })}
            options={CLEANING_CHOICES.map((d) => ({ value: d, label: label(d) }))}
          />
        }
      />

      {mayManage && (
        <SettingRow
          title={t("admin.housekeeping.sweep_now")}
          description={t("settings.maintenance.sweep_desc")}
          control={
            <button
              type="button"
              className="set-btn secondary"
              disabled={sweep.isPending}
              onClick={() => {
                setError(null);
                sweep.mutate();
              }}
            >
              {t("admin.housekeeping.sweep_now")}
            </button>
          }
        />
      )}
    </SettingsCard>
  );
}
