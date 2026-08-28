import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Overview } from "../../../api/admin";
import { fetchBackupSummary, fetchHousekeeping, fetchStorage } from "../../../api/admin";
import { useAuth } from "../../../auth/AuthContext";
import {
  IconArchive,
  IconBroom,
  IconDatabase,
  IconHardDrive,
} from "../../../components/admin/AdminIcons";
import { formatBytes } from "../../../components/admin/AdminUI";
import { MetricCard, Notice } from "../../../components/admin/SettingsKit";
import type { SectionId } from "./sections";

/**
 * The four figures worth knowing before deciding whether to open anything.
 *
 * Deliberately not a dashboard: no charts, no history, nothing that repeats what a
 * section already says better. It answers "is anything wrong, and where" - and when
 * something is, it says so in a line that names the section to go to.
 */
export default function OverviewSection({
  overview,
  onGo,
}: {
  overview: Overview;
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

  const dbBytes =
    storage.data?.categories.find((c) => c.key === "datasets")?.bytes ?? 0;

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

  return (
    <>
      <div className="set-metrics">
        <MetricCard
          icon={<IconHardDrive />}
          label={t("settings.overview.storage")}
          value={storage.data ? formatBytes(storage.data.disk_free_bytes) : "—"}
          sub={
            storage.data
              ? t("settings.overview.storage_sub", {
                  used: formatBytes(storage.data.total_bytes),
                })
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
    </>
  );
}
