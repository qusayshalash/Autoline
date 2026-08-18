import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { fetchOverview, fetchSystemStatus } from "../../api/admin";
import { IconSettings } from "../../components/admin/AdminIcons";
import { AdminPanel } from "../../components/admin/AdminUI";
import LoadingState from "../../components/LoadingState";
import BackupPanel from "./BackupPanel";
import CompactionPanel from "./CompactionPanel";
import LockoutPanel from "./LockoutPanel";
import StoragePanel from "./StoragePanel";

export default function SettingsPage() {
  const { t } = useTranslation();
  const { data: system } = useQuery({ queryKey: ["admin-system"], queryFn: fetchSystemStatus });
  const { data: overview } = useQuery({ queryKey: ["admin-overview"], queryFn: fetchOverview });

  if (!system || !overview) return <LoadingState />;

  return (
    <div className="admin-page">
      <div className="admin-columns">
        <StoragePanel />
        <BackupPanel />
        <LockoutPanel />
        <CompactionPanel />

        <AdminPanel icon={<IconSettings />} title={t("admin.settings.about")}>
          <dl className="detail-list">
            <div>
              <dt>{t("admin.system.status")}</dt>
              <dd>
                <span className="status-pill status-active">{t("admin.system.operational")}</span>
              </dd>
            </div>
            <div>
              <dt>{t("admin.system.started_at")}</dt>
              <dd>{system.started_at}</dd>
            </div>
            <div>
              <dt>{t("admin.overview.files")}</dt>
              <dd>{overview.files_total}</dd>
            </div>
            <div>
              <dt>{t("admin.overview.users_total")}</dt>
              <dd>{overview.users_total}</dd>
            </div>
            <div>
              <dt>{t("admin.overview.roles")}</dt>
              <dd>{overview.roles_total}</dd>
            </div>
          </dl>
          <p className="muted admin-note">{t("admin.settings.note")}</p>
        </AdminPanel>
      </div>
    </div>
  );
}
