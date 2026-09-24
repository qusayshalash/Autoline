import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
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
import { formatDateTime } from "../../data/datetime";
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
      {/* Three figures, not eight.
       *
       * The grid used to carry a card each for roles, permissions and enabled
       * languages - facts you check once and then know - next to two cards saying the
       * same thing about users, and a third saying what the panel below it says at
       * greater length. Eight cards of equal weight rank nothing. These three are the
       * ones that move: who is here, what is stored, how much room it takes.
       */}
      <div className="kpi-grid">
        <KpiCard
          lead
          icon={<IconUsers />}
          label={t("admin.overview.users_total")}
          value={overview.users_total.toLocaleString(i18n.language)}
          hint={t("admin.overview.inactive_hint", { count: inactive })}
          share={activeShare}
        />
        <KpiCard
          accent="primary"
          icon={<IconDatabase />}
          label={t("admin.overview.files")}
          value={overview.files_total.toLocaleString(i18n.language)}
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
      </div>

      {/* The settled facts, on one line. Still here, no longer competing with the
          figures above for the same attention. */}
      <div className="config-strip">
        <span className="config-strip-label">{t("admin.overview.configuration")}</span>
        <Link className="config-item" to="/admin/roles">
          <IconShield />
          <strong>{overview.roles_total.toLocaleString(i18n.language)}</strong>
          {t("admin.overview.roles")}
        </Link>
        <Link className="config-item" to="/admin/roles">
          <IconKey />
          <strong>{overview.permissions_total.toLocaleString(i18n.language)}</strong>
          {t("admin.overview.permissions")}
        </Link>
        <Link className="config-item" to="/admin/languages">
          <IconGlobe />
          <strong>{overview.languages_enabled.toLocaleString(i18n.language)}</strong>
          {t("admin.overview.languages")}
        </Link>
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
            <>
              <dl className="detail-list">
                <div>
                  <dt>{t("admin.system.status")}</dt>
                  <dd>
                    <span className="status-pill status-active">
                      {t("admin.system.operational")}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>{t("admin.system.storage_used")}</dt>
                  <dd>{formatBytes(system.storage_bytes)}</dd>
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

              {/* Three numbers under a total is arithmetic the reader has to do. As
                  lengths of one bar it is a shape: whether the space is the data, the
                  files it came from, or exports nobody has collected. */}
              <StorageSplit
                label={t("admin.overview.storage_split")}
                parts={[
                  { key: "datasets", bytes: system.datasets_bytes },
                  { key: "uploads", bytes: system.uploads_bytes },
                  { key: "exports", bytes: system.exports_bytes },
                ]}
              />
            </>
          ) : (
            <LoadingState />
          )}
          <p className="muted admin-note">{t("admin.system.backup_note")}</p>
        </AdminPanel>
      </div>
    </div>
  );
}

/** The storage total drawn as its parts, with a legend that names and sizes each one. */
function StorageSplit({
  label,
  parts,
}: {
  label: string;
  parts: { key: string; bytes: number }[];
}) {
  const { t } = useTranslation();
  const total = parts.reduce((sum, p) => sum + (p.bytes || 0), 0);

  return (
    <section className="storage-split">
      <h4>{label}</h4>
      <div className="split-bar" role="img" aria-label={label}>
        {parts.map((p) => (
          <span
            key={p.key}
            className={`split-seg split-part-${p.key}`}
            style={{ inlineSize: total ? `${((p.bytes || 0) / total) * 100}%` : "0%" }}
          />
        ))}
      </div>
      <ul className="split-legend">
        {parts.map((p) => (
          <li key={p.key}>
            <span className={`split-key split-part-${p.key}`} aria-hidden="true" />
            {t(`admin.system.${p.key}_size`)}
            <strong>{formatBytes(p.bytes)}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * How long the server has been up, in words.
 *
 * It used to read "3d 4h" - two Latin abbreviations on an Arabic page, which are not
 * short for anything in that language. The two largest units that are non-zero are
 * said, because "3 days and 4 hours and 12 minutes" is more precision than anyone
 * reading a status panel wants.
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
