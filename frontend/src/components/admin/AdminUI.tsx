import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import type { UserStatus } from "../../api/admin";
import { IconClose } from "./AdminIcons";

/** Which of the theme's accent colours a card is tinted with. Each maps to a token pair
 *  (solid + soft) so light and dark both stay legible without a second palette. */
export type Accent = "primary" | "success" | "warning" | "danger" | "neutral";

export function KpiCard({
  label,
  value,
  hint,
  icon,
  accent = "neutral",
  lead = false,
  share,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  accent?: Accent;
  /** the headline card of a grid: filled with the primary colour rather than tinted */
  lead?: boolean;
  /** 0-100; draws a proportion bar under the figure when the value is part of a whole */
  share?: number;
}) {
  const className = ["kpi-card", `accent-${accent}`, lead ? "lead" : ""].filter(Boolean).join(" ");
  return (
    <div className={className}>
      <span className="kpi-top">
        <span className="kpi-label">{label}</span>
        {icon && <span className="kpi-icon">{icon}</span>}
      </span>
      <strong className="kpi-value">{value}</strong>
      {(hint || share !== undefined) && (
        <span className="kpi-foot">
          {hint && <span className="kpi-hint">{hint}</span>}
          {share !== undefined && (
            <span className="kpi-track">
              <span style={{ width: `${Math.max(0, Math.min(100, share))}%` }} />
            </span>
          )}
        </span>
      )}
    </div>
  );
}

export function StatusPill({ status }: { status: UserStatus }) {
  const { t } = useTranslation();
  return <span className={`status-pill status-${status}`}>{t(`admin.status.${status}`)}</span>;
}

export function AdminPanel({
  title,
  icon,
  note,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  /** small mark beside the title, in the accent colour - the cue that tells one panel
   *  from another at a glance when several are stacked */
  icon?: ReactNode;
  /** secondary line in the header, for counts and scope */
  note?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`admin-panel ${className}`.trim()}>
      {(title || actions) && (
        <header className="admin-panel-head">
          {title && (
            <h2>
              {icon}
              <span>{title}</span>
            </h2>
          )}
          {note && <span className="admin-panel-note">{note}</span>}
          {actions && <div className="admin-panel-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

/** Slide-over used for record detail. Portaled so it is never clipped by a scrolling
 *  table, and closable by Escape or the backdrop. */
export function Drawer({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="drawer-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true">
        <header className="drawer-head">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label={t("common.close") ?? ""}>
            <IconClose />
          </button>
        </header>
        <div className="drawer-body">{children}</div>
        {footer && <footer className="drawer-foot">{footer}</footer>}
      </aside>
    </div>,
    document.body
  );
}

/**
 * A byte count as a number and a unit: "2.1 KB", "826 MB".
 *
 * Wrapped in a directional isolate, because the unit is Latin and most of this app is
 * not: dropped into an Arabic line, the bidirectional algorithm reorders the pair and
 * "2.1 KB" is rendered "KB 2.1". The isolate is two invisible characters that say "read
 * what is between us left to right, and do not let it disturb what is around it".
 *
 * Done here rather than at the call sites: there are around forty, some of them inside
 * translated sentences where there is no element to hang a dir on.
 */
export function formatBytes(bytes: number | null | undefined): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = bytes || 0;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return isolate(`${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`);
}

/** U+2066 LEFT-TO-RIGHT ISOLATE ... U+2069 POP DIRECTIONAL ISOLATE.
 *
 *  Written as escapes on purpose: both characters are invisible, and a maintainer who
 *  cannot see them cannot avoid deleting them. */
function isolate(text: string): string {
  return `⁦${text}⁩`;
}

