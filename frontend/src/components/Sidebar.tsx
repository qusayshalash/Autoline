import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import ThemeToggle from "./ThemeToggle";

const COLLAPSED_KEY = "sidebar-collapsed";

const LANGUAGES = [
  { code: "ar", name: "العربية", short: "ع" },
  { code: "he", name: "עברית", short: "עב" },
  { code: "en", name: "English", short: "EN" },
];

const icon = {
  width: 18,
  height: 18,
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function IconData() {
  return (
    <svg {...icon}>
      <rect x="2.5" y="2.5" width="15" height="15" rx="2" />
      <path d="M2.5 7.5h15M7.5 7.5v10" />
    </svg>
  );
}

function IconUsers() {
  return (
    <svg {...icon}>
      <circle cx="7.5" cy="7" r="2.8" />
      <path d="M2.5 16.5c0-2.5 2.2-4.2 5-4.2s5 1.7 5 4.2" />
      <path d="M13.5 5.2a2.6 2.6 0 0 1 0 5M14.5 12.6c2 .5 3 1.9 3 3.9" />
    </svg>
  );
}

function IconChart() {
  return (
    <svg {...icon}>
      <path d="M3 16.5h14" />
      <rect x="4" y="9" width="3" height="6" rx="1" />
      <rect x="8.5" y="5.5" width="3" height="9.5" rx="1" />
      <rect x="13" y="11.5" width="3" height="3.5" rx="1" />
    </svg>
  );
}

function IconLogout() {
  return (
    <svg {...icon}>
      <path d="M12.5 6V4.5a1.5 1.5 0 0 0-1.5-1.5H5A1.5 1.5 0 0 0 3.5 4.5v11A1.5 1.5 0 0 0 5 17h6a1.5 1.5 0 0 0 1.5-1.5V14" />
      <path d="M8.5 10h9M14.5 7l3 3-3 3" />
    </svg>
  );
}

function IconPanel() {
  return (
    <svg {...icon}>
      <rect x="2.5" y="3.5" width="15" height="13" rx="2" />
      <path d="M8 3.5v13" />
    </svg>
  );
}

export default function Sidebar() {
  const { t, i18n } = useTranslation();
  const { user, canAny, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const inDatasets = pathname === "/" || pathname.startsWith("/datasets");
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSED_KEY) === "1"
  );

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  if (!user) return null;

  const initial = user.username.charAt(0).toUpperCase();

  return (
    <aside className={collapsed ? "sidebar collapsed" : "sidebar"}>
      <div className="sidebar-head">
        <svg className="sidebar-logo" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
          <rect x="2" y="2" width="28" height="28" rx="8" fill="var(--primary)" />
          <rect x="9" y="10" width="14" height="3" rx="1.5" fill="#fff" />
          <rect x="9" y="15.5" width="10" height="3" rx="1.5" fill="#fff" opacity="0.85" />
          <rect x="9" y="21" width="6" height="3" rx="1.5" fill="#fff" opacity="0.6" />
        </svg>
        {!collapsed && <span className="sidebar-title">{t("app_title")}</span>}
      </div>

      <button
        type="button"
        className="sidebar-collapse"
        onClick={() => setCollapsed((c) => !c)}
        aria-label={collapsed ? t("nav.expand_sidebar") : t("nav.collapse_sidebar")}
        title={collapsed ? t("nav.expand_sidebar") ?? "" : t("nav.collapse_sidebar") ?? ""}
      >
        <IconPanel />
      </button>

      <nav className="sidebar-nav">
        {/* every dataset screen (import, cleaning, explorer) lives under Datasets, so the
            entry stays highlighted while you work inside a file */}
        <NavLink
          to="/"
          title={t("nav.datasets") ?? ""}
          className={inDatasets ? "active" : undefined}
        >
          <IconData />
          {!collapsed && <span>{t("nav.datasets")}</span>}
        </NavLink>
        <NavLink to="/statistics" title={t("statistics.title") ?? ""}>
          <IconChart />
          {!collapsed && <span>{t("statistics.title")}</span>}
        </NavLink>
        {canAny(
          "system.view",
          "users.view",
          "roles.view",
          "languages.manage",
          "activity.view"
        ) && (
          <NavLink to="/admin" title={t("admin.title") ?? ""}>
            <IconUsers />
            {!collapsed && <span>{t("admin.title")}</span>}
          </NavLink>
        )}
      </nav>

      <div className="sidebar-foot">
        <ThemeToggle collapsed={collapsed} />

        <div className={collapsed ? "sidebar-lang collapsed" : "sidebar-lang"}>
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              className={i18n.language.split("-")[0] === l.code ? "active" : ""}
              onClick={() => i18n.changeLanguage(l.code)}
              title={l.name}
            >
              {collapsed ? l.short : l.name}
            </button>
          ))}
        </div>

        <div className="sidebar-user" title={`${user.username} · ${t(`auth.role_${user.role}`)}`}>
          <span className="sidebar-avatar">{initial}</span>
          {!collapsed && (
            <span className="sidebar-user-text">
              <strong>{user.username}</strong>
              <small>{t(`auth.role_${user.role}`)}</small>
            </span>
          )}
          <button
            type="button"
            className="sidebar-logout"
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
            aria-label={t("auth.logout")}
            title={t("auth.logout") ?? ""}
          >
            <IconLogout />
          </button>
        </div>
      </div>
    </aside>
  );
}
