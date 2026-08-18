import type { TFunction } from "i18next";
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
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
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

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** Timestamps arrive as UTC strings from DuckDB; show them in the viewer's locale. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const iso = value.includes("T") ? value : value.replace(" ", "T") + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

export function formatRelative(value: string | null | undefined, t: TFunction): string {
  if (!value) return "—";
  const iso = value.includes("T") ? value : value.replace(" ", "T") + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return value;
  const secs = Math.round((Date.now() - d.getTime()) / 1000);
  if (secs < 60) return t("admin.time.just_now");
  if (secs < 3600) return t("admin.time.minutes", { count: Math.floor(secs / 60) });
  if (secs < 86400) return t("admin.time.hours", { count: Math.floor(secs / 3600) });
  return t("admin.time.days", { count: Math.floor(secs / 86400) });
}
