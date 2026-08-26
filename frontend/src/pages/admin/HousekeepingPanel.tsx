import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchHousekeeping, setHousekeeping, sweepHousekeeping } from "../../api/admin";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconDatabase } from "../../components/admin/AdminIcons";
import { AdminPanel } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";

/** Offered periods, in days. 0 is off. */
const JOB_CHOICES = [0, 30, 90, 365] as const;
const CLEANING_CHOICES = [0, 90, 365, 730] as const;

/**
 * The automatic sweep over the catalog's two append-only tables.
 *
 * This panel is a window onto something that already runs, not a switch that starts it.
 * Both figures below are usually zero, and that is the point: the rows are removed on a
 * schedule, so what the screen mostly reports is that there is nothing to report.
 *
 * The one number worth understanding is the held count. An export's row is what tells
 * the download endpoint the file's format, so an old export whose file is still on disk
 * keeps its row past its date - it is not overdue, it is in use.
 */
export default function HousekeepingPanel() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [swept, setSwept] = useState<number | null>(null);

  const mayManage = can("system.manage");

  const { data } = useQuery({
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
      setSwept(null);
      refresh();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const sweep = useMutation({
    mutationFn: sweepHousekeeping,
    onSuccess: (result) => {
      setSwept(result.jobs_removed + result.cleaning_removed);
      refresh();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  if (!data) return null;

  const lang = i18n.language;
  const n = (value: number) => value.toLocaleString(lang);
  const label = (days: number) =>
    days === 0 ? t("admin.housekeeping.off") : t("admin.housekeeping.days", { count: days });

  return (
    <AdminPanel
      icon={<IconDatabase />}
      title={t("admin.housekeeping.title")}
      note={t("admin.housekeeping.rows", { count: n(data.jobs_total + data.cleaning_total) })}
    >
      <ErrorBanner message={error} />
      <p className="muted admin-note">{t("admin.housekeeping.hint")}</p>

      <p className="drawer-section">{t("admin.housekeeping.jobs")}</p>
      <p className="muted admin-note">{t("admin.housekeeping.jobs_hint")}</p>
      <div className="storage-retention" role="group" aria-label={t("admin.housekeeping.jobs") ?? ""}>
        {JOB_CHOICES.map((days) => (
          <button
            key={days}
            type="button"
            className={data.jobs_retention_days === days ? "active" : ""}
            disabled={!mayManage || retention.isPending}
            onClick={() => retention.mutate({ jobs_retention_days: days })}
          >
            {label(days)}
          </button>
        ))}
      </div>
      <p className="admin-note">
        {t("admin.housekeeping.jobs_state", {
          total: n(data.jobs_total),
          due: n(data.jobs_due),
        })}
      </p>
      {data.jobs_held_by_exports > 0 && (
        <p className="muted admin-note">
          {t("admin.housekeeping.held", { count: n(data.jobs_held_by_exports) })}
        </p>
      )}

      <p className="drawer-section">{t("admin.housekeeping.cleaning")}</p>
      <p className="muted admin-note">{t("admin.housekeeping.cleaning_hint")}</p>
      <div
        className="storage-retention"
        role="group"
        aria-label={t("admin.housekeeping.cleaning") ?? ""}
      >
        {CLEANING_CHOICES.map((days) => (
          <button
            key={days}
            type="button"
            className={data.cleaning_retention_days === days ? "active" : ""}
            disabled={!mayManage || retention.isPending}
            onClick={() => retention.mutate({ cleaning_retention_days: days })}
          >
            {label(days)}
          </button>
        ))}
      </div>
      <p className="admin-note">
        {t("admin.housekeeping.cleaning_state", {
          total: n(data.cleaning_total),
          due: n(data.cleaning_due),
        })}
      </p>

      {mayManage && (
        <div className="storage-actions">
          <button
            type="button"
            className="btn secondary"
            disabled={sweep.isPending}
            onClick={() => {
              setError(null);
              sweep.mutate();
            }}
          >
            {t("admin.housekeeping.sweep_now")}
          </button>
          {swept !== null && (
            <span className="backup-progress" role="status">
              {swept === 0
                ? t("admin.housekeeping.nothing_due")
                : t("admin.housekeeping.swept", { count: n(swept) })}
            </span>
          )}
        </div>
      )}
    </AdminPanel>
  );
}
