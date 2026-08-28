import { useTranslation } from "react-i18next";

import type { Overview, SystemStatus } from "../../../api/admin";
import { IconInfo } from "../../../components/admin/AdminIcons";
import { SettingsCard, StatusBadge } from "../../../components/admin/SettingsKit";

/**
 * What the server is, rather than anything you can change here.
 *
 * Key/value rows rather than a card per figure: five numbers do not need five borders,
 * and the point of this section is to be readable at a glance when somebody is checking
 * whether the thing they are looking at is the machine they think it is.
 */
export default function SystemInfoSection({
  system,
  overview,
}: {
  system: SystemStatus;
  overview: Overview;
}) {
  const { t, i18n } = useTranslation();
  const n = (v: number) => v.toLocaleString(i18n.language);

  return (
    <SettingsCard
      icon={<IconInfo />}
      title={t("admin.settings.about")}
      description={t("admin.settings.note")}
    >
      {/* A grid of facts, not five full-width rows and not five cards. Each of these is a
          short value with a short label, which is exactly the shape that reads fastest
          two or three across. */}
      <dl className="set-facts">
        <div className="set-fact">
          <dt>{t("admin.system.status")}</dt>
          <dd>
            <StatusBadge tone="healthy">{t("admin.system.operational")}</StatusBadge>
          </dd>
        </div>
        <div className="set-fact">
          <dt>{t("admin.system.started_at")}</dt>
          <dd>{system.started_at}</dd>
        </div>
        <div className="set-fact">
          <dt>{t("admin.overview.files")}</dt>
          <dd>{n(overview.files_total)}</dd>
        </div>
        <div className="set-fact">
          <dt>{t("admin.overview.users_total")}</dt>
          <dd>{n(overview.users_total)}</dd>
        </div>
        <div className="set-fact">
          <dt>{t("admin.overview.roles")}</dt>
          <dd>{n(overview.roles_total)}</dd>
        </div>
      </dl>
    </SettingsCard>
  );
}
