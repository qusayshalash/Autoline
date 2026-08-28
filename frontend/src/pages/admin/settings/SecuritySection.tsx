import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { clearLockout, fetchLockouts } from "../../../api/admin";
import { apiErrorMessage } from "../../../api/client";
import { useAuth } from "../../../auth/AuthContext";
import { IconCheckCircle, IconShield } from "../../../components/admin/AdminIcons";
import {
  EmptyState,
  SettingsCard,
  StatusBadge,
} from "../../../components/admin/SettingsKit";
import { useToast } from "../../../components/admin/Toaster";
import ErrorBanner from "../../../components/ErrorBanner";

/** Locks expire on their own, so the list goes stale without a refresh. */
const REFRESH_MS = 15_000;

/**
 * Accounts and addresses currently held off after repeated failed logins.
 *
 * This is the recourse that makes a temporary lock acceptable. A lock can be triggered
 * by somebody else guessing at a colleague's username, and without somewhere to see and
 * lift it, that colleague waits with no explanation and nobody able to help.
 *
 * The empty state is the normal one and says so rather than disappearing - "nothing is
 * locked" is information too, and a panel that vanishes cannot be checked.
 */
export default function SecuritySection() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);

  const { data: lockouts } = useQuery({
    queryKey: ["admin-lockouts"],
    queryFn: fetchLockouts,
    refetchInterval: REFRESH_MS,
  });

  const clear = useMutation({
    mutationFn: clearLockout,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-lockouts"] });
      toast("success", t("settings.security.unlocked"));
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const canClear = can("users.update");
  const count = lockouts?.length ?? 0;

  return (
    <SettingsCard
      icon={<IconShield />}
      title={t("admin.lockouts.title")}
      description={t("admin.lockouts.hint")}
      actions={
        <StatusBadge tone={count > 0 ? "warning" : "healthy"}>
          {count > 0 ? t("admin.lockouts.count", { count }) : t("admin.lockouts.none")}
        </StatusBadge>
      }
      bodyless
    >
      {error && (
        <div style={{ padding: "0 22px" }}>
          <ErrorBanner message={error} />
        </div>
      )}

      {count === 0 ? (
        <EmptyState
          icon={<IconCheckCircle />}
          title={t("admin.lockouts.none")}
          description={t("settings.security.empty_desc")}
        />
      ) : (
        <div className="set-table-wrap">
          <table className="set-table">
            <thead>
              <tr>
                <th>{t("admin.lockouts.subject")}</th>
                <th>{t("admin.lockouts.kind")}</th>
                <th className="num">{t("admin.lockouts.failures")}</th>
                <th className="num">{t("admin.lockouts.unlocks_in")}</th>
                <th className="shrink" />
              </tr>
            </thead>
            <tbody>
              {lockouts!.map((l) => (
                <tr key={l.key}>
                  <td>
                    <span className="set-path">
                      <bdi>{l.subject}</bdi>
                    </span>
                  </td>
                  <td>{t(`admin.lockouts.kind_${l.kind}`)}</td>
                  <td className="num">{l.failures.toLocaleString(i18n.language)}</td>
                  <td className="num">
                    {t("admin.lockouts.minutes", {
                      minutes: Math.max(1, Math.ceil(l.retry_after_s / 60)),
                    })}
                  </td>
                  <td className="shrink">
                    {canClear && (
                      <button
                        type="button"
                        className="set-btn secondary small"
                        disabled={clear.isPending}
                        onClick={() => clear.mutate(l.key)}
                      >
                        {t("admin.lockouts.unlock")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SettingsCard>
  );
}
