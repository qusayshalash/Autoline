import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { formatNumber } from "../../data/numbers";
import type { TFunction } from "i18next";
import { Link } from "react-router-dom";

import { fetchActivity, fetchOverview, fetchSystemStatus } from "../../api/admin";
import {
  IconActivity,
  IconDatabase,
  IconGlobe,
  IconKey,
  IconSettings,
  IconShield,
  IconUsers,
} from "../../components/admin/AdminIcons";
import { AdminPanel, KpiCard, formatBytes } from "../../components/admin/AdminUI";
import { formatDateTime, formatRelative } from "../../data/datetime";
import QueryState from "../../components/QueryState";
import LoadingState from "../../components/LoadingState";
import ActivityRow from "./ActivityRow";

export default function OverviewPage() {
  const { t, i18n } = useTranslation();

  const { data: overview, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin-overview"],
    queryFn: fetchOverview,
    refetchInterval: 30_000,
  });
  const { data: system } = useQuery({
    queryKey: ["admin-system"],
    queryFn: fetchSystemStatus,
    refetchInterval: 30_000,
  });
  const { data: activity } = useQuery({
    queryKey: ["admin-activity", "recent"],
    queryFn: () => fetchActivity({ limit: 8 }),
    refetchInterval: 30_000,
  });

  // isError has to be checked explicitly: on failure isLoading goes false while
  // overview stays undefined, and a "!overview" guard alone shows the spinner forever
  if (isLoading || isError || !overview) {
    return <QueryState loading={isLoading} error={isError ? error : null} onRetry={refetch} />;
  }

  const inactive = overview.users_total - overview.users_active;
  const activeShare =
    overview.users_total > 0 ? (overview.users_active * 100) / overview.users_total : 0;

  return (
    <div className="admin-page">
      <div className="kpi-grid">
        <KpiCard
          lead
          icon={<IconUsers />}
          label={t("admin.overview.users_total")}
          value={formatNumber(overview.users_total, i18n.language)}
          hint={t("admin.overview.inactive_hint", { count: inactive })}
          share={activeShare}
        />
        <KpiCard
          accent="success"
          icon={<IconUsers />}
          label={t("admin.overview.users_active")}
          value={formatNumber(overview.users_active, i18n.language)}
          hint={`${Math.round(activeShare)}%`}
          share={activeShare}
        />
        <KpiCard
          accent="primary"
          icon={<IconShield />}
          label={t("admin.overview.roles")}
          value={formatNumber(overview.roles_total, i18n.language)}
        />
        <KpiCard
          accent="primary"
          icon={<IconKey />}
          label={t("admin.overview.permissions")}
          value={formatNumber(overview.permissions_total, i18n.language)}
        />
        <KpiCard
          accent="warning"
          icon={<IconGlobe />}
          label={t("admin.overview.languages")}
          value={formatNumber(overview.languages_enabled, i18n.language)}
        />
        <KpiCard
          accent="primary"
          icon={<IconDatabase />}
          label={t("admin.overview.files")}
          value={formatNumber(overview.files_total, i18n.language)}
          hint={t("admin.overview.rows_hint", {
            formatted: overview.files_rows.toLocaleString(i18n.language),
          })}
        />
        <KpiCard
          accent="warning"
          icon={<IconDatabase />}
          label={t("admin.overview.files_size")}
          value={formatBytes(overview.files_bytes)}
        />
        <KpiCard
          accent="success"
          icon={<IconActivity />}
          label={t("admin.overview.last_activity")}
          value={
            overview.last_activity
              ? t(`admin.actions.${overview.last_activity.action}`, {
                  defaultValue: overview.last_activity.action,
                })
              : "—"
          }
          hint={
            overview.last_activity
              ? formatRelative(overview.last_activity.at, t, i18n.language)
              : undefined
          }
        />
      </div>

      <div className="admin-columns">
        <AdminPanel
          icon={<IconActivity />}
          title={t("admin.overview.recent_activity")}
          actions={
            <Link className="admin-link" to="/admin/activity">
              {t("admin.overview.view_all")}
            </Link>
          }
        >
          {activity && activity.items.length > 0 ? (
            <ul className="activity-list">
              {activity.items.map((item) => (
                <ActivityRow key={item.id} item={item} />
              ))}
            </ul>
          ) : (
            <p className="muted">{t("admin.overview.no_activity")}</p>
          )}
        </AdminPanel>

        <AdminPanel icon={<IconSettings />} title={t("admin.overview.system_status")}>
          {system ? (
            <dl className="detail-list">
              <div>
                <dt>{t("admin.system.status")}</dt>
                <dd>
                  <span className="status-pill status-active">{t("admin.system.operational")}</span>
                </dd>
              </div>
              <div>
                <dt>{t("admin.system.storage_used")}</dt>
                <dd>{formatBytes(system.storage_bytes)}</dd>
              </div>
              <div>
                <dt>{t("admin.system.datasets_size")}</dt>
                <dd>{formatBytes(system.datasets_bytes)}</dd>
              </div>
              <div>
                <dt>{t("admin.system.uploads_size")}</dt>
                <dd>{formatBytes(system.uploads_bytes)}</dd>
              </div>
              <div>
                <dt>{t("admin.system.exports_size")}</dt>
                <dd>{formatBytes(system.exports_bytes)}</dd>
              </div>
              <div>
                <dt>{t("admin.system.started_at")}</dt>
                <dd>{formatDateTime(system.started_at, i18n.language)}</dd>
              </div>
              <div>
                <dt>{t("admin.system.uptime")}</dt>
                <dd>{formatUptime(system.uptime_seconds, t)}</dd>
              </div>
            </dl>
          ) : (
            <LoadingState />
          )}
          <p className="muted admin-note">{t("admin.system.backup_note")}</p>
        </AdminPanel>
      </div>

      {overview.last_activity && (
        <p className="muted admin-footnote">
          {t("admin.overview.last_admin_action", {
            actor: overview.last_activity.actor_username,
            when: formatDateTime(overview.last_activity.at, i18n.language),
          })}
        </p>
      )}
    </div>
  );
}

/**
 * How long the server has been up, in words.
 *
 * It used to read "3d 4h" - two Latin abbreviations on an Arabic page, which are not
 * short for anything in that language. The two largest non-zero units are said, because
 * "3 days and 4 hours and 12 minutes" is more precision than a status panel wants.
 */
function formatUptime(seconds: number, t: TFunction): string {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  const said: string[] = [];
  if (days) said.push(t("admin.system.up_days", { count: days }));
  if (days || hours) said.push(t("admin.system.up_hours", { count: hours }));
  if (!days) said.push(t("admin.system.up_minutes", { count: minutes }));

  return said.slice(0, 2).join(t("admin.system.uptime_join"));
}
