import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { clearLockout, fetchLockouts } from "../../api/admin";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconShield } from "../../components/admin/AdminIcons";
import { AdminPanel } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";
import { useState } from "react";

/** Locks expire on their own, so the list goes stale without a refresh. */
const REFRESH_MS = 15_000;

/**
 * Accounts and addresses currently held off after repeated failed logins.
 *
 * This panel is the recourse that makes a temporary lock acceptable. A lock can be
 * triggered by somebody else guessing at a colleague's username, and without somewhere to
 * see and lift it, that colleague waits with no explanation and nobody able to help.
 *
 * An empty panel is the normal state and says so, rather than disappearing - "nothing is
 * locked" is information too, and a panel that vanishes cannot be checked.
 */
export default function LockoutPanel() {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: lockouts } = useQuery({
    queryKey: ["admin-lockouts"],
    queryFn: fetchLockouts,
    refetchInterval: REFRESH_MS,
  });

  const clear = useMutation({
    mutationFn: clearLockout,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-lockouts"] }),
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const canClear = can("users.update");

  return (
    <AdminPanel
      icon={<IconShield />}
      title={t("admin.lockouts.title")}
      note={
        lockouts && lockouts.length > 0
          ? t("admin.lockouts.count", { count: lockouts.length })
          : t("admin.lockouts.none")
      }
    >
      <ErrorBanner message={error} />
      <p className="muted admin-note">{t("admin.lockouts.hint")}</p>

      {lockouts && lockouts.length > 0 && (
        <div className="quality-table-wrap">
          <table className="quality-table">
            <thead>
              <tr>
                <th>{t("admin.lockouts.subject")}</th>
                <th>{t("admin.lockouts.kind")}</th>
                <th className="num">{t("admin.lockouts.failures")}</th>
                <th className="num">{t("admin.lockouts.unlocks_in")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lockouts.map((l) => (
                <tr key={l.key}>
                  <td className="mono wrap">{l.subject}</td>
                  <td>{t(`admin.lockouts.kind_${l.kind}`)}</td>
                  <td className="num">{l.failures.toLocaleString(i18n.language)}</td>
                  <td className="num">
                    {t("admin.lockouts.minutes", {
                      minutes: Math.max(1, Math.ceil(l.retry_after_s / 60)),
                    })}
                  </td>
                  <td className="num">
                    {canClear && (
                      <button
                        type="button"
                        className="btn secondary small"
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
    </AdminPanel>
  );
}
