import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import type { ActivityItem } from "../../api/admin";
import { formatBytes } from "../../components/admin/AdminUI";
import { formatInstant, formatTimeOfDay } from "../../data/datetime";

/** Colour family per action group, so a log skimmed at speed still reads. */
function toneFor(action: string): string {
  if (action.endsWith(".deleted")) return "danger";
  if (action.endsWith(".created")) return "success";
  if (action.startsWith("auth.")) return "muted";
  return "info";
}

/**
 * The line under the action: "9 → 8 rows", "encoding utf_8 · delimiter ','".
 *
 * The server sends both a sentence and a key. The sentence is English and is what every
 * entry written before the key existed has, so it stays as the fallback; the key is the
 * only form that can be read in the reader's language. An unrecognised key falls back
 * the same way, which is what lets a server run ahead of the interface.
 */
function detailFor(item: ActivityItem, t: TFunction): string {
  if (!item.detail_code) return item.detail;

  const params: Record<string, unknown> = { ...item.detail_params };

  // A byte count travels as a number so it can be shown the way the rest of the app
  // shows sizes. "22170243 بايت" is technically the freed space and practically
  // unreadable.
  if (typeof params.bytes === "number") {
    params.bytes = formatBytes(params.bytes);
  }

  // `fields` is a list of column names - role, status, permissions - and each one is a
  // word the reader should see in their own language rather than as it is spelled in
  // the database.
  if (Array.isArray(params.fields)) {
    params.fields = params.fields
      .map((field) => t(`admin.fields.${String(field)}`, { defaultValue: String(field) }))
      .join(t("common.list_separator"));
  }

  return t(`admin.details.${item.detail_code}`, { ...params, defaultValue: item.detail });
}

export default function ActivityRow({ item }: { item: ActivityItem }) {
  const { t, i18n } = useTranslation();
  const label = t(`admin.actions.${item.action}`, { defaultValue: item.action });
  const detail = detailFor(item, t);

  // "qa_admin signed in qa_admin": for a sign-in the target is the person who signed
  // in, which is the actor, and the line said the name twice.
  const target = item.target_label === item.actor_username ? "" : item.target_label;

  return (
    <li className="activity-item">
      <span className={`activity-dot tone-${toneFor(item.action)}`} aria-hidden="true" />
      <span className="activity-text">
        <span className="activity-main">
          <strong dir="auto">{item.actor_username}</strong> {label}
          {target && <em dir="auto"> {target}</em>}
        </span>
        {detail && <span className="activity-detail">{detail}</span>}
      </span>
      {/* The day is the heading above this row, so the row carries the clock time -
          which is the part that orders one entry against the next within it. The full
          instant, to the second, stays in the tooltip. */}
      <time className="activity-time" title={formatInstant(item.at, i18n.language)}>
        {formatTimeOfDay(item.at, i18n.language)}
      </time>
    </li>
  );
}
