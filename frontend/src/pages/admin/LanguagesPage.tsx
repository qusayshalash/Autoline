import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchLanguages, updateLanguages } from "../../api/admin";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconGlobe } from "../../components/admin/AdminIcons";
import { AdminPanel } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";
import LoadingState from "../../components/LoadingState";

export default function LanguagesPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: languages, isLoading } = useQuery({
    queryKey: ["admin-languages"],
    queryFn: fetchLanguages,
  });

  const save = useMutation({
    mutationFn: (body: { enabled?: string[]; default?: string }) => updateLanguages(body),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["admin-languages"] });
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
      qc.invalidateQueries({ queryKey: ["admin-activity"] });
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  if (isLoading || !languages) return <LoadingState />;

  const editable = can("languages.manage");
  const enabledCodes = languages.filter((l) => l.enabled).map((l) => l.code);

  return (
    <div className="admin-page">
      <AdminPanel icon={<IconGlobe />} title={t("admin.languages.title")}>
        <p className="muted admin-note">{t("admin.languages.note")}</p>
        <ErrorBanner message={error} />
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t("admin.languages.language")}</th>
                <th>{t("admin.languages.code")}</th>
                <th>{t("admin.languages.direction")}</th>
                <th>{t("admin.languages.enabled")}</th>
                <th>{t("admin.languages.default")}</th>
              </tr>
            </thead>
            <tbody>
              {languages.map((l) => {
                const lastEnabled = l.enabled && enabledCodes.length === 1;
                return (
                  <tr key={l.code}>
                    <td>
                      <strong>{l.native_name}</strong> <span className="muted">{l.name}</span>
                    </td>
                    <td className="mono">{l.code}</td>
                    <td className="mono">{l.direction.toUpperCase()}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={l.enabled}
                        // the default language and the last remaining one cannot be turned
                        // off - either would leave the app with no usable language
                        disabled={!editable || l.is_default || lastEnabled}
                        title={
                          l.is_default
                            ? t("admin.languages.cannot_disable_default") ?? ""
                            : lastEnabled
                              ? t("admin.languages.cannot_disable_last") ?? ""
                              : ""
                        }
                        onChange={() =>
                          save.mutate({
                            enabled: l.enabled
                              ? enabledCodes.filter((c) => c !== l.code)
                              : [...enabledCodes, l.code],
                          })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="radio"
                        name="default-language"
                        checked={l.is_default}
                        disabled={!editable || !l.enabled}
                        onChange={() => save.mutate({ default: l.code })}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </AdminPanel>
    </div>
  );
}
