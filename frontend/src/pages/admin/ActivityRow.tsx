import { useTranslation } from "react-i18next";

import type { ActivityItem } from "../../api/admin";
import { formatDateTime, formatRelative } from "../../components/admin/AdminUI";

/** Colour family per action group, so a log skimmed at speed still reads. */
function toneFor(action: string): string {
  if (action.endsWith(".deleted")) return "danger";
  if (action.endsWith(".created")) return "success";
  if (action.startsWith("auth.")) return "muted";
  return "info";
}

export default function ActivityRow({ item }: { item: ActivityItem }) {
  const { t } = useTranslation();
  const label = t(`admin.actions.${item.action}`, { defaultValue: item.action });

  return (
    <li className="activity-item">
      <span className={`activity-dot tone-${toneFor(item.action)}`} aria-hidden="true" />
      <span className="activity-text">
        <span className="activity-main">
          <strong>{item.actor_username}</strong> {label}
          {item.target_label && <em> {item.target_label}</em>}
        </span>
        {item.detail && <span className="activity-detail">{item.detail}</span>}
      </span>
      <time className="activity-time" title={formatDateTime(item.at)}>
        {formatRelative(item.at, t)}
      </time>
    </li>
  );
}
