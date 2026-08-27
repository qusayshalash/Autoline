import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchActivityPurgePlan, purgeActivity } from "../../api/admin";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconActivity, IconTrash } from "../../components/admin/AdminIcons";
import { AdminPanel } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";

/** Offered cutoffs. Nothing shorter than a quarter: the trail's value is that it reaches
 *  back further than the memory of whatever is being investigated. */
const CUTOFFS = [90, 180, 365, 730] as const;

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
 * The count is fetched before anything is removed, so the confirmation names a real
 * number, and the purge writes itself into the trail it just shortened.
 */
export default function ActivityTrimPanel() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [days, setDays] = useState<number>(DEFAULT_CUTOFF);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<number | null>(null);

  const mayPurge = can("activity.purge");

  const plan = useQuery({
    queryKey: ["activity-purge-plan", days],
    queryFn: () => fetchActivityPurgePlan(days),
    enabled: mayPurge,
  });

  const purge = useMutation({
    mutationFn: () => purgeActivity(days),
    onSuccess: (result) => {
      setDone(result.removed);
      setConfirming(false);
      queryClient.invalidateQueries({ queryKey: ["admin-activity"] });
      queryClient.invalidateQueries({ queryKey: ["activity-purge-plan"] });
      queryClient.invalidateQueries({ queryKey: ["admin-overview"] });
    },
    onError: (e) => {
      setError(apiErrorMessage(e, t("common.error_generic")));
      setConfirming(false);
    },
  });

  // The panel is hidden rather than disabled for everyone else. A control that exists but
  // never works reads as a fault; the permission is held by one role by design.
  if (!mayPurge) return null;

  const removable = plan.data?.removed ?? 0;
  const lang = i18n.language;

  return (
    <AdminPanel
      icon={<IconActivity />}
      title={t("admin.activity_trim.title")}
      note={
        plan.data
          ? t("admin.activity_trim.remaining", {
              count: plan.data.remaining.toLocaleString(lang),
            })
          : undefined
      }
    >
      <ErrorBanner message={error} />
      <p className="muted admin-note">{t("admin.activity_trim.hint")}</p>

      <div className="storage-retention" role="group" aria-label={t("admin.activity_trim.cutoff") ?? ""}>
        {CUTOFFS.map((d) => (
          <button
            key={d}
            type="button"
            className={days === d ? "active" : ""}
            onClick={() => {
              setDays(d);
              setConfirming(false);
              setDone(null);
            }}
          >
            {t("admin.activity_trim.days", { count: d })}
          </button>
        ))}
      </div>

      <p className="admin-note">
        {removable > 0
          ? t("admin.activity_trim.will_remove", { count: removable.toLocaleString(lang) })
          : t("admin.activity_trim.nothing_to_remove")}
      </p>

      {done !== null && (
        <p className="admin-note" role="status">
          {t("admin.activity_trim.removed_done", { count: done.toLocaleString(lang) })}
        </p>
      )}

      <div className="storage-actions">
        {confirming ? (
          <>
            <button
              type="button"
              className="btn danger"
              disabled={purge.isPending}
              onClick={() => purge.mutate()}
            >
              <IconTrash />
              {t("admin.activity_trim.confirm", { count: removable.toLocaleString(lang) })}
            </button>
            <button type="button" className="btn secondary" onClick={() => setConfirming(false)}>
              {t("common.cancel")}
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn danger"
            disabled={removable === 0 || plan.isFetching}
            onClick={() => {
              setError(null);
              setDone(null);
              setConfirming(true);
            }}
          >
            <IconTrash />
            {t("admin.activity_trim.purge")}
          </button>
        )}
      </div>
    </AdminPanel>
  );
}
