import { useQuery } from "@tanstack/react-query";
import { useCallback, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { fetchOverview, fetchSystemStatus } from "../../api/admin";
import { useAuth } from "../../auth/AuthContext";
import {
  IconActivity,
  IconArchive,
  IconBroom,
  IconHardDrive,
  IconInfo,
  IconOverview,
  IconShield,
} from "../../components/admin/AdminIcons";
import { Toaster } from "../../components/admin/Toaster";
import QueryState from "../../components/QueryState";
import BackupsSection from "./settings/BackupsSection";
import LogsSection from "./settings/LogsSection";
import MaintenanceSection from "./settings/MaintenanceSection";
import OverviewSection from "./settings/OverviewSection";
import SecuritySection from "./settings/SecuritySection";
import StorageSection from "./settings/StorageSection";
import SystemInfoSection from "./settings/SystemInfoSection";
import { isSectionId, type SectionId } from "./settings/sections";

/**
 * System settings.
 *
 * One category at a time rather than every panel at once. The page this replaced put
 * seven equally-weighted cards on one scroll, so finding a setting meant reading all of
 * them and nothing said which were dangerous. Here the categories are a list you pick
 * from, the active one is in the URL so it can be linked and survives a reload, and
 * severity is carried by the control rather than by the card.
 *
 * Sections whose content the viewer cannot reach are dropped from the list rather than
 * shown empty - an entry that leads to nothing is worse than no entry.
 */
export default function SettingsPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();

  const system = useQuery({ queryKey: ["admin-system"], queryFn: fetchSystemStatus });
  const overview = useQuery({ queryKey: ["admin-overview"], queryFn: fetchOverview });

  const go = useCallback(
    (id: SectionId) => {
      const next = new URLSearchParams(params);
      next.set("section", id);
      setParams(next, { replace: true });
      document.querySelector(".admin-content")?.scrollTo({ top: 0 });
    },
    [params, setParams]
  );

  const items: { id: SectionId; label: string; icon: ReactNode; shown: boolean }[] = [
    { id: "overview", label: t("settings.nav.overview"), icon: <IconOverview />, shown: true },
    {
      id: "storage",
      label: t("settings.nav.storage"),
      icon: <IconHardDrive />,
      shown: can("system.view"),
    },
    {
      id: "backups",
      label: t("settings.nav.backups"),
      icon: <IconArchive />,
      shown: can("system.view"),
    },
    {
      id: "maintenance",
      label: t("settings.nav.maintenance"),
      icon: <IconBroom />,
      shown: can("system.view"),
    },
    {
      id: "logs",
      label: t("settings.nav.logs"),
      icon: <IconActivity />,
      shown: can("activity.purge"),
    },
    {
      id: "security",
      label: t("settings.nav.security"),
      icon: <IconShield />,
      shown: can("activity.view"),
    },
    { id: "system", label: t("settings.nav.system"), icon: <IconInfo />, shown: true },
  ];
  const available = items.filter((i) => i.shown);

  const requested = params.get("section");
  const active: SectionId =
    isSectionId(requested) && available.some((i) => i.id === requested) ? requested : "overview";

  const failed = system.error ?? overview.error;
  if (failed || !system.data || !overview.data) {
    return (
      <QueryState
        loading={system.isLoading || overview.isLoading}
        error={failed}
        onRetry={() => {
          system.refetch();
          overview.refetch();
        }}
      />
    );
  }

  return (
    <Toaster>
      {/* No page header here: the admin layout's topbar already carries the title, the
          description and the health badge for every admin page, and a second one would
          say the same three things twice. */}
      <div className="settings-page">
        <div className="settings-body">
          <nav className="settings-nav" aria-label={t("admin.nav.settings") ?? ""}>
            {available.map((item) => (
              <button
                key={item.id}
                type="button"
                className={item.id === active ? "active" : ""}
                aria-current={item.id === active ? "page" : undefined}
                onClick={() => go(item.id)}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </nav>

          <div className="settings-nav-select">
            <select
              className="set-select"
              value={active}
              aria-label={t("admin.nav.settings") ?? ""}
              onChange={(e) => go(e.target.value as SectionId)}
            >
              {available.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div className="settings-sections">
            {active === "overview" && (
              <OverviewSection overview={overview.data} system={system.data} onGo={go} />
            )}
            {active === "storage" && <StorageSection />}
            {active === "backups" && <BackupsSection />}
            {active === "maintenance" && <MaintenanceSection />}
            {active === "logs" && <LogsSection />}
            {active === "security" && <SecuritySection />}
            {active === "system" && (
              <SystemInfoSection system={system.data} overview={overview.data} />
            )}
          </div>
        </div>
      </div>
    </Toaster>
  );
}
