import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";

import { listDatasets } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import ThemeToggle from "../ThemeToggle";
import { IconBack, IconChart, IconFile, IconPanel } from "./StatsIcons";

const COLLAPSED_KEY = "stats-sidebar-collapsed";

const LANGUAGES = [
  { code: "ar", name: "العربية", short: "ع" },
  { code: "he", name: "עברית", short: "עב" },
  { code: "en", name: "English", short: "EN" },
];

/**
 * The Statistics area's own shell.
 *
 * Deliberately not the data workspace's chrome: this screen answers "how does the file
 * break down?", never "what is in row 12,000", so it carries no grid, no pagination and
 * no column tools. What it does carry is the file list, because switching files is the
 * one navigation that belongs here.
 */
export default function StatsLayout() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { datasetId } = useParams();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === "1");

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets"],
    queryFn: listDatasets,
  });
  const ready = datasets.filter((d) => d.status === "ready");
  const current = ready.find((d) => d.id === datasetId);

  return (
    <div className="stats-shell">
      <aside className={collapsed ? "stats-sidebar collapsed" : "stats-sidebar"}>
        <div className="stats-brand">
          <span className="stats-brand-mark">
            <IconChart />
          </span>
          {!collapsed && <span className="stats-brand-text">{t("statistics.title")}</span>}
        </div>

        <button
          type="button"
          className="stats-collapse"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? t("nav.expand_sidebar") : t("nav.collapse_sidebar")}
          title={collapsed ? t("nav.expand_sidebar") ?? "" : t("nav.collapse_sidebar") ?? ""}
        >
          <IconPanel />
        </button>

        <nav className="stats-nav">
          {!collapsed && <p className="stats-nav-label">{t("statistics.files")}</p>}
          {ready.map((d) => (
            <NavLink
              key={d.id}
              to={`/statistics/${d.id}`}
              title={d.original_filename}
              className="stats-file"
            >
              <IconFile />
              {!collapsed && (
                <span className="stats-file-text">
                  <strong>{d.original_filename}</strong>
                  <small>
                    {(d.row_count_cleaned ?? d.row_count_raw ?? 0).toLocaleString(i18n.language)}{" "}
                    {t("explorer.rows")}
                  </small>
                </span>
              )}
            </NavLink>
          ))}
          {ready.length === 0 && !collapsed && (
            <p className="stats-nav-empty">{t("statistics.no_files")}</p>
          )}
        </nav>

        <div className="stats-sidebar-foot">
          <button type="button" className="stats-exit" onClick={() => navigate("/")}>
            <IconBack />
            {!collapsed && <span>{t("statistics.back_to_data")}</span>}
          </button>

          <ThemeToggle collapsed={collapsed} />

          <div className={collapsed ? "stats-lang collapsed" : "stats-lang"}>
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                type="button"
                className={i18n.language.split("-")[0] === l.code ? "active" : ""}
                onClick={() => i18n.changeLanguage(l.code)}
                title={l.name}
              >
                {collapsed ? l.short : l.name}
              </button>
            ))}
          </div>

          <div className="stats-account" title={user?.username}>
            <span className="stats-avatar">{(user?.username ?? "?").charAt(0).toUpperCase()}</span>
            {!collapsed && (
              <span className="stats-account-text">
                <strong>{user?.full_name || user?.username}</strong>
                <small>{user?.role}</small>
              </span>
            )}
            <button
              type="button"
              className="stats-logout"
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
              aria-label={t("auth.logout")}
              title={t("auth.logout") ?? ""}
            >
              <IconBack />
            </button>
          </div>
        </div>
      </aside>

      <div className="stats-main">
        <header className="stats-topbar">
          <div className="stats-topbar-title">
            <h1>{t("statistics.heading")}</h1>
            {current && (
              <p>
                {current.original_filename}
                <span className="dot" />
                {(current.row_count_cleaned ?? current.row_count_raw ?? 0).toLocaleString(
                  i18n.language
                )}{" "}
                {t("explorer.rows")}
                {current.updated_at && (
                  <>
                    <span className="dot" />
                    {t("statistics.updated_at", {
                      when: new Date(current.updated_at.replace(" ", "T")).toLocaleString(
                        i18n.language
                      ),
                    })}
                  </>
                )}
              </p>
            )}
          </div>
        </header>
        <div className="stats-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
