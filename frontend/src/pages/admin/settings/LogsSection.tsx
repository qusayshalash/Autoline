import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchActivity, fetchActivityPurgePlan, purgeActivity } from "../../../api/admin";
import { apiErrorMessage } from "../../../api/client";
import { useAuth } from "../../../auth/AuthContext";
import { IconActivity } from "../../../components/admin/AdminIcons";
import {
  Choice,
  ConfirmDialog,
  SettingRow,
  SettingsCard,
  StatusBadge,
} from "../../../components/admin/SettingsKit";
import { useToast } from "../../../components/admin/Toaster";
import ErrorBanner from "../../../components/ErrorBanner";
import { formatDateTime } from "../../../data/datetime";

/** Offered cutoffs. Nothing shorter than a quarter: the trail's value is that it reaches
 *  back further than the memory of whatever is being investigated. */
const CUTOFFS = [90, 180, 365, 730];
const DEFAULT_CUTOFF = 365;

/**
 * Trimming the audit trail by age.
 *
 * The trail is otherwise append-only, and that is the point: a record an administrator
 * can edit proves nothing, because the first line worth erasing is the one somebody
 * wanted gone. What is offered here is a cutoff and nothing else - no deleting an entry,
 * an actor, or an action - because age is the only filter that cannot be aimed at a
 * particular event.
 *
 * Nothing happens on a schedule. The count is fetched before anything is removed, so the
 * confirmation names a real number, and the purge writes itself into the trail it just
 * shortened.
 */
export default function LogsSection() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [days, setDays] = useState<number>(DEFAULT_CUTOFF);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mayPurge = can("activity.purge");

  const plan = useQuery({
    queryKey: ["activity-purge-plan", days],
    queryFn: () => fetchActivityPurgePlan(days),
    enabled: mayPurge,
  });

  // The trail records its own trimming, so the last one is simply the newest entry with
  // that action - no extra state to keep, and it cannot disagree with the log.
  const lastTrim = useQuery({
    queryKey: ["activity", "activity.purged", 1],
    queryFn: () => fetchActivity({ action: "activity.purged", limit: 1 }),
    enabled: mayPurge,
  });

  const purge = useMutation({
    mutationFn: () => purgeActivity(days),
    onSuccess: (result) => {
      setConfirming(false);
      queryClient.invalidateQueries({ queryKey: ["admin-activity"] });
      queryClient.invalidateQueries({ queryKey: ["activity-purge-plan"] });
      queryClient.invalidateQueries({ queryKey: ["admin-overview"] });
      queryClient.invalidateQueries({ queryKey: ["activity", "activity.purged"] });
      toast(
        "success",
        t("admin.activity_trim.removed_done", {
          count: result.removed.toLocaleString(i18n.language),
        })
      );
    },
    onError: (e) => {
      setConfirming(false);
      setError(apiErrorMessage(e, t("common.error_generic")));
    },
  });

  if (!mayPurge) return null;

  const removable = plan.data?.removed ?? 0;
  const n = (v: number) => v.toLocaleString(i18n.language);

  return (
    <>
      <SettingsCard
        icon={<IconActivity />}
        title={t("admin.activity_trim.title")}
        description={t("settings.logs.desc")}
        actions={
          plan.data ? (
            <StatusBadge tone="neutral">
              {t("admin.activity_trim.remaining", { count: n(plan.data.remaining) })}
            </StatusBadge>
          ) : undefined
        }
        bodyless
      >
        {error && (
          <div style={{ padding: "0 22px" }}>
            <ErrorBanner message={error} />
          </div>
        )}

        <SettingRow
          title={t("settings.logs.policy")}
          description={t("settings.logs.policy_desc")}
          hint={t("admin.activity_trim.hint")}
          control={
            <Choice
              value={days}
              disabled={plan.isFetching}
              ariaLabel={t("settings.logs.policy")}
              onChange={(d) => {
                setDays(d);
                setError(null);
              }}
              options={CUTOFFS.map((d) => ({
                value: d,
                label: t("admin.activity_trim.days", { count: d }),
              }))}
            />
          }
        />

        <SettingRow
          title={t("settings.logs.matching")}
          description={t("settings.logs.matching_desc", { days })}
          control={
            <StatusBadge tone={removable > 0 ? "warning" : "neutral"}>
              {t("settings.logs.matching_count", { count: n(removable) })}
            </StatusBadge>
          }
        />

        <SettingRow
          title={t("settings.logs.last_trim")}
          description={t("settings.logs.last_trim_desc")}
          control={
            <span className="set-row-desc" style={{ margin: 0 }}>
              {lastTrim.data?.items?.[0]?.at
                ? formatDateTime(lastTrim.data.items[0].at as string, i18n.language)
                : t("settings.logs.never_trimmed")}
            </span>
          }
        />

        <SettingRow
          title={t("admin.activity_trim.purge")}
          description={t("settings.logs.manual_note")}
          control={
            /* Disabled rather than red when there is nothing to remove: a destructive
               button that would do nothing still reads as a threat, and offering it
               invites a click that has to be answered with "nothing happened". */
            <button
              type="button"
              className={removable > 0 ? "set-btn danger" : "set-btn secondary"}
              disabled={removable === 0 || plan.isFetching}
              onClick={() => {
                setError(null);
                setConfirming(true);
              }}
            >
              {removable > 0
                ? t("settings.logs.purge_count", { count: n(removable) })
                : t("admin.activity_trim.purge")}
            </button>
          }
        />
      </SettingsCard>

      <ConfirmDialog
        open={confirming}
        danger
        busy={purge.isPending}
        title={t("settings.logs.confirm_title")}
        body={t("settings.logs.confirm_body", { count: n(removable), days })}
        confirmLabel={t("admin.activity_trim.confirm", { count: n(removable) })}
        onCancel={() => setConfirming(false)}
        onConfirm={() => purge.mutate()}
      />
    </>
  );
}
