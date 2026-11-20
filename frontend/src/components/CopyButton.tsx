import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

/**
 * A small button that puts one value on the clipboard - a plate, a chassis number, an
 * engine code: the things read out over the phone or typed into a supplier's site, where
 * one wrong character is a wrong part. It turns into a tick for a moment so the copy is
 * seen to have happened, and says what it copied to a screen reader.
 */
export default function CopyButton({ value, label }: { value: string; label: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // no clipboard (an insecure page, or the browser refused): the value is on screen
    }
  }

  const name = copied ? t("copy.copied") : t("copy.copy_what", { what: label });
  return (
    <button
      type="button"
      className={`copy-btn${copied ? " is-copied" : ""}`}
      onClick={copy}
      title={name}
      aria-label={name}
    >
      {copied ? (
        <svg viewBox="0 0 20 20" width={14} height={14} fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4.5 10.5l3.5 3.5 7.5-8" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" width={14} height={14} fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="7" y="7" width="9.5" height="9.5" rx="2" />
          <path d="M13 7V5a1.5 1.5 0 0 0-1.5-1.5h-6A1.5 1.5 0 0 0 4 5v6a1.5 1.5 0 0 0 1.5 1.5H7" />
        </svg>
      )}
      <span className="sr-only" aria-live="polite">
        {copied ? t("copy.copied") : ""}
      </span>
    </button>
  );
}
