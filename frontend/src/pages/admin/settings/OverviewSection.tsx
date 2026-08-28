import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Overview, SystemStatus } from "../../../api/admin";
import { fetchBackupSummary, fetchHousekeeping, fetchStorage } from "../../../api/admin";
import { useAuth } from "../../../auth/AuthContext";
import {
  IconArchive,
  IconBroom,
  IconArrow,
  IconDatabase,
  IconHardDrive,
  IconInfo,
  IconZap,
} from "../../../components/admin/AdminIcons";
import { formatBytes } from "../../../components/admin/AdminUI";
import {
  MetricCard,
  Notice,
  SettingsCard,
  StatusBadge,
} from "../../../components/admin/SettingsKit";
import type { SectionId } from "./sections";

/**
 * What is worth knowing before opening anything else.
 *
 * Four figures, then whatever is wrong, then the two states that answer "how full" and
 * "is it well", then the way into the three controls people actually come here for.
 *
 * The quick actions navigate rather than act, and are named as destinations for that
 * reason: a button reading "take a backup now" that only scrolls you to the backup
 * button would be lying about what the click does.
 */
export default function OverviewSection({
  overview,
  system,
  onGo,
}: {
  overview: Overview;
  system: SystemStatus;
  onGo: (id: SectionId) => void;
}) {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const maySeeSystem = can("system.view");

  const storage = useQuery({
    queryKey: ["admin-storage"],
    queryFn: fetchStorage,
    enabled: maySeeSystem,
  });
  const backups = useQuery({
    queryKey: ["admin-backup-summary"],
    queryFn: fetchBackupSummary,
    enabled: maySeeSystem,
  });
  const housekeeping = useQuery({
    queryKey: ["admin-housekeeping"],
    queryFn: fetchHousekeeping,
    enabled: maySeeSystem,
  });

  const n = (v: number) => v.toLocaleString(i18n.language);
  const dbBytes = storage.data?.categories.find((c) => c.key === "datasets")?.bytes ?? 0;

  const warnings: { text: string; go: SectionId }[] = [];
  if (backups.data?.stale) {
    warnings.push({
      text:
        backups.data.hours_since_last === null
          ? t("admin.backup.stale_never")
          : t("admin.backup.stale_since", { hours: Math.round(backups.data.hours_since_last) }),
      go: "backups",
    });
  }
  if (backups.data?.same_disk_as_data) {
    warnings.push({ text: t("admin.backup.same_disk_warning"), go: "backups" });
  }

  // Used against the whole disk, not against itself: "2.3 GB of 27.3 GB" is the figure
  // that says whether there is room, which a breakdown of the 2.3 alone cannot.
  const used = storage.data?.total_bytes ?? 0;
  const free = storage.data?.disk_free_bytes ?? 0;
  const capacity = used + free;
  const usedPct = capacity > 0 ? (used / capacity) * 100 : 0;

  return (
    <>
      <div className="set-metrics">
        <MetricCard
          icon={<IconHardDrive />}
          label={t("settings.overview.storage")}
          value={storage.data ? formatBytes(free) : "—"}
          sub={
            storage.data
              ? t("settings.overview.storage_sub", { used: formatBytes(used) })
              : undefined
          }
        />
        <MetricCard
          icon={<IconDatabase />}
          label={t("settings.overview.database")}
          value={storage.data ? formatBytes(dbBytes) : "—"}
          sub={t("settings.overview.database_sub", { count: n(overview.files_total) })}
        />
        <MetricCard
          icon={<IconArchive />}
          label={t("settings.overview.backups")}
          value={backups.data ? n(backups.data.verified_count) : "—"}
          sub={
            backups.data?.latest_at
              ? t("settings.overview.backups_sub", {
                  when: new Date(backups.data.latest_at).toLocaleDateString(i18n.language),
                })
              : t("admin.backup.never")
          }
        />
        <MetricCard
          icon={<IconBroom />}
          label={t("settings.overview.records")}
          value={
            housekeeping.data
              ? n(housekeeping.data.jobs_total + housekeeping.data.cleaning_total)
              : "—"
          }
          sub={
            housekeeping.data
              ? t("settings.overview.records_sub", {
                  count: n(housekeeping.data.jobs_due + housekeeping.data.cleaning_due),
                })
              : undefined
          }
        />
      </div>

      {warnings.length > 0 && (
        <div className="set-notices" style={{ marginBottom: 0 }}>
          {warnings.map((w) => (
            <Notice key={w.text} tone="warning">
              {w.text}{" "}
              <button type="button" className="set-table-linkish" onClick={() => onGo(w.go)}>
                {t("settings.overview.go_fix")}
              </button>
            </Notice>
          ))}
        </div>
      )}

      <div className="set-duo">
        <SettingsCard
          icon={<IconHardDrive />}
          title={t("settings.overview.storage_state")}
          actions={
            <StatusBadge tone={usedPct >= 90 ? "critical" : usedPct >= 75 ? "warning" : "healthy"}>
              {t("settings.overview.used_pct", { pct: Math.round(usedPct) })}
            </StatusBadge>
          }
        >
          {storage.data ? (
            <>
              <div className="set-gauge-head">
                <strong>{formatBytes(used)}</strong>
                <span>{t("settings.overview.of_capacity", { total: formatBytes(capacity) })}</span>
              </div>
              <div className="set-stack">
                <i className="db" style={{ width: `${usedPct}%` }} />
              </div>
              <dl className="set-kv" style={{ marginTop: 4 }}>
                {[...storage.data.categories]
                  .filter((c) => c.bytes > 0)
                  .sort((a, b) => b.bytes - a.bytes)
                  .slice(0, 3)
                  .map((c) => (
                    <div key={c.key}>
                      <dt>{t(`admin.storage.category.${c.key}`)}</dt>
                      <dd>{formatBytes(c.bytes)}</dd>
                    </div>
                  ))}
              </dl>
            </>
          ) : (
            <p className="set-row-desc">—</p>
          )}
        </SettingsCard>

        <SettingsCard
          icon={<IconInfo />}
          title={t("settings.overview.system_state")}
          actions={<StatusBadge tone="healthy">{t("admin.system.operational")}</StatusBadge>}
        >
          <dl className="set-kv">
            <div>
              <dt>{t("admin.system.started_at")}</dt>
              <dd>{system.started_at}</dd>
            </div>
            <div>
              <dt>{t("admin.overview.users_total")}</dt>
              <dd>{n(overview.users_total)}</dd>
            </div>
            <div>
              <dt>{t("admin.overview.files")}</dt>
              <dd>{n(overview.files_total)}</dd>
            </div>
            <div>
              <dt>{t("admin.overview.roles")}</dt>
              <dd>{n(overview.roles_total)}</dd>
            </div>
          </dl>
        </SettingsCard>
      </div>

      {maySeeSystem && (
        <SettingsCard
          icon={<IconZap />}
          title={t("settings.overview.quick_title")}
          description={t("settings.overview.quick_desc")}
        >
          <div className="set-quick">
            <button type="button" className="set-btn secondary" onClick={() => onGo("backups")}>
              {t("settings.backups.run_title")}
              <IconArrow />
            </button>
            <button type="button" className="set-btn secondary" onClick={() => onGo("storage")}>
              {t("admin.storage.cleanup")}
              <IconArrow />
            </button>
            <button type="button" className="set-btn secondary" onClick={() => onGo("storage")}>
              {t("admin.compaction.title")}
              <IconArrow />
            </button>
          </div>
        </SettingsCard>
      )}
    </>
  );
}
