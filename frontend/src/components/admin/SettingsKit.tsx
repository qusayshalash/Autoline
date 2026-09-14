import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import {
  IconAlert,
  IconCheckCircle,
  IconCopy,
  IconInfo,
} from "./AdminIcons";

// Moved out so the pages outside settings can ask the same question the same way.
export { ConfirmDialog } from "../ConfirmDialog";

/**
 * The pieces every settings section is built from.
 *
 * They exist so the page has one answer to each question - what a card looks like, what
 * a setting row looks like, how a destructive action asks before it acts - instead of
 * seven panels each inventing their own. The rules they encode:
 *
 *   - a card is a category, and never contains another card;
 *   - a setting is a row: name, one line of description, one control;
 *   - a long explanation belongs in a hint bubble, not in the page;
 *   - anything irreversible goes through ConfirmDialog, and only that dialog is allowed
 *     to be loud about it.
 */

export type Tone = "healthy" | "warning" | "critical" | "neutral";

/* --- card ------------------------------------------------------------------ */

export function SettingsCard({
  icon,
  title,
  description,
  actions,
  children,
  bodyless,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  actions?: ReactNode;
  children?: ReactNode;
  /** For a card whose body is only rows or a table, which bring their own padding. */
  bodyless?: boolean;
}) {
  return (
    <section className="set-card">
      <header className="set-card-head">
        {icon}
        <div style={{ minWidth: 0 }}>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {actions && <div className="set-card-head-actions">{actions}</div>}
      </header>
      {children && <div className={bodyless ? "set-card-rows" : "set-card-body"}>{children}</div>}
    </section>
  );
}

/* --- setting row ----------------------------------------------------------- */

export function SettingRow({
  title,
  description,
  hint,
  control,
  children,
  stacked,
}: {
  title: string;
  description?: string;
  /** Longer rationale. Lives behind an info icon so the page stays scannable. */
  hint?: string;
  control?: ReactNode;
  children?: ReactNode;
  stacked?: boolean;
}) {
  return (
    <div className={stacked ? "set-row stacked" : "set-row"}>
      <div className="set-row-main">
        <div className="set-row-title">
          {title}
          {hint && <HelpHint text={hint} />}
        </div>
        {description && <p className="set-row-desc">{description}</p>}
        {children}
      </div>
      {control && <div className="set-row-control">{control}</div>}
    </div>
  );
}

/* --- help bubble ----------------------------------------------------------- */

export function HelpHint({ text }: { text: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const bubbleId = useId();
  // The button is named for what it does and *described* by what it says. Naming it
  // with the paragraph made a screen reader read three sentences of explanation where
  // it should have read one word, on every row of every settings page - and then read
  // the same three sentences again when the bubble opened.
  return (
    <button
      type="button"
      className="set-hint"
      aria-label={t("common.help") ?? ""}
      aria-expanded={open}
      aria-describedby={open ? bubbleId : undefined}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={(e) => {
        e.preventDefault();
        setOpen((v) => !v);
      }}
    >
      <IconInfo />
      {open && (
        <span className="set-hint-bubble" id={bubbleId} role="tooltip">
          {text}
        </span>
      )}
    </button>
  );
}

/* --- badges ---------------------------------------------------------------- */

export function StatusBadge({
  tone,
  children,
  plain,
}: {
  tone: Tone;
  children: ReactNode;
  plain?: boolean;
}) {
  return <span className={`set-badge ${tone}${plain ? " plain" : ""}`}>{children}</span>;
}

/* --- metric ---------------------------------------------------------------- */

export function MetricCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="set-metric">
      <span className="set-metric-label">
        {icon}
        {label}
      </span>
      <span className="set-metric-value">{value}</span>
      {sub && <span className="set-metric-sub">{sub}</span>}
    </div>
  );
}

/* --- notice ---------------------------------------------------------------- */

export function Notice({
  tone = "info",
  children,
}: {
  tone?: "info" | "warning" | "success";
  children: ReactNode;
}) {
  return (
    <div className={`set-notice ${tone}`}>
      {tone === "warning" ? <IconAlert /> : tone === "success" ? <IconCheckCircle /> : <IconInfo />}
      <span>{children}</span>
    </div>
  );
}

/* --- select ---------------------------------------------------------------- */

export function Choice<T extends number | string>({
  value,
  options,
  onChange,
  disabled,
  ariaLabel,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  const isNumeric = typeof value === "number";
  return (
    <select
      className="set-select"
      value={String(value)}
      disabled={disabled}
      aria-label={ariaLabel}
      onChange={(e) => onChange((isNumeric ? Number(e.target.value) : e.target.value) as T)}
    >
      {options.map((o) => (
        <option key={String(o.value)} value={String(o.value)}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/* --- path ------------------------------------------------------------------ */

/** A filesystem path, forced LTR. Arabic page direction otherwise reorders the segments
 *  into something that reads plausibly and points nowhere. */
export function PathValue({ children }: { children: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  return (
    <span className="set-path">
      <button
        type="button"
        className="set-copy"
        title={copied ? t("common.copied") ?? "" : t("common.copy") ?? ""}
        aria-label={t("common.copy") ?? ""}
        onClick={() => {
          navigator.clipboard?.writeText(children).then(
            () => {
              setCopied(true);
              timer.current = window.setTimeout(() => setCopied(false), 1600);
            },
            () => undefined
          );
        }}
      >
        {copied ? <IconCheckCircle /> : <IconCopy />}
      </button>
      <bdi>{children}</bdi>
    </span>
  );
}

/* --- empty state ----------------------------------------------------------- */

export function EmptyState({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
}) {
  return (
    <div className="set-empty">
      {icon}
      <strong>{title}</strong>
      {description && <p>{description}</p>}
    </div>
  );
}

/* --- progress -------------------------------------------------------------- */

export function Working({ label }: { label: string }) {
  return (
    <span className="set-progress" role="status">
      <span className="set-spinner" />
      {label}
    </span>
  );
}

