import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { firstAllowedPath } from "../auth/permissionRoutes";
import EmptyState from "../components/EmptyState";

export default function ForbiddenPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const destination = firstAllowedPath(user?.permissions ?? []);

  return (
    <main className="permission-page" dir={i18n.dir()}>
      <div className="card permission-card">
        <EmptyState message={t("common.access_denied")} />
        <p>{t("common.access_denied_help")}</p>
        {destination !== "/forbidden" && (
          <Link className="btn secondary" to={destination}>
            {t("common.go_to_available_area")}
          </Link>
        )}
      </div>
    </main>
  );
}
