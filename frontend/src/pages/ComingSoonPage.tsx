import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

/**
 * Stands in for the vehicle catalog while it is on hold. The page itself (CatalogPage)
 * and its API stay in place; only the route points here, so turning it back on is one
 * line in App.tsx.
 */
export default function ComingSoonPage() {
  const { t, i18n } = useTranslation();

  return (
    <main className="permission-page" dir={i18n.dir()}>
      <div className="card permission-card">
        <h1>{t("catalog.coming_soon")}</h1>
        <p>{t("catalog.coming_soon_help")}</p>
        <Link className="btn secondary" to="/">
          {t("catalog.back")}
        </Link>
      </div>
    </main>
  );
}
