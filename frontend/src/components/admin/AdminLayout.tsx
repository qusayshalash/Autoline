import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import ThemeToggle from "../ThemeToggle";
import {
  IconActivity,
  IconBack,
  IconFiles,
  IconGlobe,
  IconOverview,
  IconPanel,
  IconSettings,
  IconShield,
  IconUsers,
} from "./AdminIcons";

const COLLAPSED_KEY = "admin-sidebar-collapsed";

/** Nav entries and the permission each one needs. An entry the user cannot use is not
 *  rendered at all - the API would refuse it anyway, so showing it would only mislead. */
const NAV = [
  { to: "/admin", end: true, key: "overview", icon: IconOverview, permission: "system.view" },
  { to: "/admin/users", key: "users", icon: IconUsers, permission: "users.view" },
  { to: "/admin/roles", key: "roles", icon: IconShield, permission: "roles.view" },
  { to: "/admin/languages", key: "languages", icon: IconGlobe, permission: "languages.manage" },
  { to: "/admin/files", key: "files", icon: IconFiles, permission: "datasets.view" },
  { to: "/admin/activity", key: "activity", icon: IconActivity, permission: "activity.view" },
  { to: "/admin/settings", key: "settings", icon: IconSettings, permission: "system.view" },
];

export default function AdminLayout() {
  const { t } = useTranslation();
  const { user, can } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === "1");

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const visible = NAV.filter((n) => can(n.permission));
  const current = visible.find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
  const backTo = can("datasets.view") ? "/" : (visible[0]?.to ?? "/forbidden");

  return (
    <div className="admin-shell">
      <aside className={collapsed ? "admin-sidebar collapsed" : "admin-sidebar"}>
        <div className="admin-brand">
          <span className="admin-brand-mark">⌘</span>
          {!collapsed && <span className="admin-brand-text">{t("admin.title")}</span>}
        </div>

        <button
          type="button"
          className="admin-collapse"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? t("nav.expand_sidebar") : t("nav.collapse_sidebar")}
          title={collapsed ? t("nav.expand_sidebar") ?? "" : t("nav.collapse_sidebar") ?? ""}
        >
          <IconPanel />
        </button>

        <nav className="admin-nav">
          {!collapsed && <p className="admin-nav-label">{t("admin.nav_section")}</p>}
          {visible.map(({ to, end, key, icon: Icon }) => (
            <NavLink key={to} to={to} end={end} title={t(`admin.nav.${key}`) ?? ""}>
              <Icon />
              {!collapsed && <span>{t(`admin.nav.${key}`)}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="admin-sidebar-foot">
          <ThemeToggle collapsed={collapsed} />

          <button type="button" className="admin-exit" onClick={() => navigate(backTo)}>
            <IconBack />
            {!collapsed && <span>{t("admin.back_to_app")}</span>}
          </button>
          <div className="admin-account" title={user?.username}>
            <span className="admin-avatar">{(user?.username ?? "?").charAt(0).toUpperCase()}</span>
            {!collapsed && (
              <span className="admin-account-text">
                <strong>{user?.full_name || user?.username}</strong>
                <small>{user?.role}</small>
              </span>
            )}
          </div>
        </div>
      </aside>

      <div className="admin-main">
        <header className="admin-topbar">
          <div className="admin-topbar-title">
            <h1>{current ? t(`admin.nav.${current.key}`) : t("admin.title")}</h1>
            <p>{current ? t(`admin.blurb.${current.key}`) : t("admin.blurb.overview")}</p>
          </div>
          <span className="admin-topbar-badge">
            <span className="dot" />
            {t("admin.system.operational")}
          </span>
        </header>
        <div className="admin-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
