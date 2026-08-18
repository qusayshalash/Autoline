import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
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
import {
  AdminPanel,
  KpiCard,
  formatBytes,
  formatDateTime,
  formatRelative,
} from "../../components/admin/AdminUI";
import LoadingState from "../../components/LoadingState";
import ActivityRow from "./ActivityRow";

export default function OverviewPage() {
  const { t } = useTranslation();

  const { data: overview, isLoading } = useQuery({
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

  if (isLoading || !overview) return <LoadingState />;

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
          value={overview.users_total.toLocaleString()}
          hint={t("admin.overview.inactive_hint", { count: inactive })}
          share={activeShare}
        />
        <KpiCard
          accent="success"
          icon={<IconUsers />}
          label={t("admin.overview.users_active")}
          value={overview.users_active.toLocaleString()}
          hint={`${Math.round(activeShare)}%`}
          share={activeShare}
        />
        <KpiCard
          accent="primary"
          icon={<IconShield />}
          label={t("admin.overview.roles")}
          value={overview.roles_total.toLocaleString()}
        />
        <KpiCard
          accent="primary"
          icon={<IconKey />}
          label={t("admin.overview.permissions")}
          value={overview.permissions_total.toLocaleString()}
        />
        <KpiCard
          accent="warning"
          icon={<IconGlobe />}
          label={t("admin.overview.languages")}
          value={overview.languages_enabled.toLocaleString()}
        />
        <KpiCard
          accent="primary"
          icon={<IconDatabase />}
          label={t("admin.overview.files")}
          value={overview.files_total.toLocaleString()}
          hint={t("admin.overview.rows_hint", { count: overview.files_rows.toLocaleString() })}
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
          hint={overview.last_activity ? formatRelative(overview.last_activity.at, t) : undefined}
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
                <dd>{system.started_at}</dd>
              </div>
              <div>
                <dt>{t("admin.system.uptime")}</dt>
                <dd>{formatUptime(system.uptime_seconds)}</dd>
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
            when: formatDateTime(overview.last_activity.at),
          })}
        </p>
      )}
    </div>
  );
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}
