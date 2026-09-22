import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchLanguages, updateLanguages, type Language } from "../../api/admin";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconGlobe, IconInfo, IconLock } from "../../components/admin/AdminIcons";
import { AdminPanel } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";
import QueryState from "../../components/QueryState";

/**
 * Which languages the interface offers, and which one it opens in.
 *
 * Edited as a draft and saved once, rather than a switch at a time. The two settings
 * constrain each other - the default language cannot be disabled, and the last enabled
 * one cannot be either - so a person changing both has to pass through a state the
 * server would have to reject. Holding the change here lets them arrive at the pair they
 * meant and send it in one request, which is also the shape the endpoint takes.
 */
export default function LanguagesPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const {
    data: languages,
    isLoading,
    isError: loadFailed,
    error: loadError,
    refetch,
  } = useQuery({
    queryKey: ["admin-languages"],
    queryFn: fetchLanguages,
  });

  // the draft: what is on screen, which is the saved state until something is touched
  const [enabled, setEnabled] = useState<string[] | null>(null);
  const [fallback, setFallback] = useState<string | null>(null);

  // Re-seeded whenever the server's answer changes, so a save - or somebody else's -
  // lands on screen instead of being masked by a stale draft.
  useEffect(() => {
    if (!languages) return;
    setEnabled(languages.filter((l) => l.enabled).map((l) => l.code));
    setFallback(languages.find((l) => l.is_default)?.code ?? null);
  }, [languages]);

  const save = useMutation({
    mutationFn: (body: { enabled: string[]; default: string }) => updateLanguages(body),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["admin-languages"] });
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
      qc.invalidateQueries({ queryKey: ["admin-activity"] });
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  if (isLoading || loadFailed || !languages || enabled === null) {
    return (
      <QueryState loading={isLoading} error={loadFailed ? loadError : null} onRetry={refetch} />
    );
  }

  const editable = can("languages.manage");
  const savedEnabled = languages.filter((l) => l.enabled).map((l) => l.code);
  const savedDefault = languages.find((l) => l.is_default)?.code ?? null;
  const dirty =
    fallback !== savedDefault ||
    enabled.length !== savedEnabled.length ||
    savedEnabled.some((c) => !enabled.includes(c));

  function reset() {
    setEnabled(savedEnabled);
    setFallback(savedDefault);
    setError(null);
  }

  /** Turning a language on also makes it available to be the default; turning one off
   *  is refused for the two languages the app cannot do without. */
  function toggle(code: string) {
    setEnabled((prev) => {
      const current = prev ?? [];
      if (!current.includes(code)) return [...current, code];
      if (code === fallback || current.length === 1) return current;
      return current.filter((c) => c !== code);
    });
  }

  /** The default is always enabled, so choosing one that is off turns it on. */
  function makeDefault(code: string) {
    setFallback(code);
    setEnabled((prev) => (prev?.includes(code) ? prev : [...(prev ?? []), code]));
  }

  return (
    <div className="admin-page">
      <AdminPanel
        icon={<IconGlobe />}
        title={
          <>
            {t("admin.languages.available")}
            <span className="count-badge">{languages.length}</span>
          </>
        }
      >
        <p className="admin-callout">
          <IconInfo />
          <span>{t("admin.languages.note")}</span>
        </p>
        <ErrorBanner message={error} />

        <div className="admin-table-wrap">
          <table className="admin-table lang-table">
            <thead>
              <tr>
                <th>{t("admin.languages.language")}</th>
                <th>{t("admin.languages.code")}</th>
                <th>{t("admin.languages.writing_direction")}</th>
                <th>{t("admin.languages.activation")}</th>
                <th>{t("admin.languages.default")}</th>
              </tr>
            </thead>
            <tbody>
              {languages.map((l) => {
                const on = enabled.includes(l.code);
                const isDefault = l.code === fallback;
                const locked = isDefault || (on && enabled.length === 1);
                return (
                  <tr key={l.code} className={isDefault ? "is-default" : undefined}>
                    <td>
                      <span className="lang-cell">
                        <span className="lang-mark" aria-hidden="true">
                          {markFor(l)}
                        </span>
                        <span className="lang-names">
                          <strong>
                            {l.native_name}
                            {isDefault && (
                              <span className="lang-chip">{t("admin.languages.default")}</span>
                            )}
                          </strong>
                          <span>{l.name}</span>
                        </span>
                      </span>
                    </td>
                    <td>
                      <span className="code-chip">{l.code}</span>
                    </td>
                    <td>
                      <span className="lang-direction">
                        <span>{t(`admin.languages.direction_${l.direction}`)}</span>
                        <span className="mono">{l.direction.toUpperCase()}</span>
                      </span>
                    </td>
                    <td>
                      <span className="lang-switch">
                        <label className="switch">
                          <input
                            type="checkbox"
                            checked={on}
                            aria-label={
                              t("admin.languages.enable", { language: l.native_name }) ?? ""
                            }
                            disabled={!editable || locked}
                            onChange={() => toggle(l.code)}
                          />
                          <span className="switch-track" aria-hidden="true" />
                        </label>
                        <span className={on ? "switch-state on" : "switch-state"}>
                          {on
                            ? t("admin.languages.state_on")
                            : t("admin.languages.state_off")}
                        </span>
                        {locked && (
                          <span
                            className="lang-lock"
                            title={
                              isDefault
                                ? t("admin.languages.cannot_disable_default") ?? ""
                                : t("admin.languages.cannot_disable_last") ?? ""
                            }
                          >
                            <IconLock />
                          </span>
                        )}
                      </span>
                    </td>
                    <td>
                      <input
                        type="radio"
                        name="default-language"
                        className="lang-radio"
                        aria-label={
                          t("admin.languages.make_default", { language: l.native_name }) ?? ""
                        }
                        checked={isDefault}
                        disabled={!editable}
                        onChange={() => makeDefault(l.code)}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {editable && (
          <footer className="lang-foot">
            <p className="lang-foot-note">
              <IconLock />
              <span>{t("admin.languages.default_stays_on")}</span>
            </p>
            <div className="lang-foot-actions">
              <button
                type="button"
                className="set-btn secondary"
                onClick={reset}
                disabled={!dirty || save.isPending}
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="set-btn primary"
                disabled={!dirty || save.isPending}
                onClick={() => fallback && save.mutate({ enabled, default: fallback })}
              >
                {save.isPending ? t("common.saving") : t("admin.languages.save_changes")}
              </button>
            </div>
          </footer>
        )}
      </AdminPanel>
    </div>
  );
}

/**
 * The letter on a language's tile.
 *
 * Its own first letter, in its own script - so the tile reads as that language rather
 * than as a label about it. Arabic and Hebrew have no capitals, and toUpperCase leaves
 * them exactly as they are.
 */
function markFor(l: Language): string {
  const source = (l.native_name || l.code).trim();
  return (Array.from(source)[0] ?? "?").toUpperCase();
}
