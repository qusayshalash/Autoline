import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { IconAlert, IconInfo } from "./admin/AdminIcons";

/**
 * The one way this app asks "are you sure?".
 *
 * It lives out here rather than in the settings kit because the actions worth asking
 * about are not only in settings - deleting a file, a role, an account. Those used to
 * call window.confirm, which is a different dialog in a different direction: the
 * browser draws it left-to-right with buttons in the operating system's language, and
 * it cannot follow the app's theme. On an Arabic right-to-left product the question
 * arrived translated inside a frame that was not.
 *
 * Reach for it through useConfirm() rather than rendering it directly; see
 * ConfirmProvider.
 */

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="set-dialog-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div className="set-dialog" role="alertdialog" aria-modal="true" aria-label={title}>
        <div className={`set-dialog-icon ${danger ? "danger" : "normal"}`}>
          {danger ? <IconAlert /> : <IconInfo />}
        </div>
        <h3>{title}</h3>
        <p>{body}</p>
        <div className="set-dialog-actions">
          <button type="button" className="set-btn secondary" onClick={onCancel} disabled={busy}>
            {t("common.cancel")}
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={`set-btn ${danger ? "danger-solid" : "primary"}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
