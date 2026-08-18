import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import type { ColumnKind } from "../api/client";
import ColumnSelect from "./ColumnSelect";
import { IconClose, IconColumns, IconPlusCircle, IconReset, IconTrash } from "./SheetIcons";

interface Props {
  open: boolean;
  columns: string[];
  groupBy: string[];
  kindByColumn?: Map<string, ColumnKind>;
  onApply: (groupBy: string[]) => void;
  onClose: () => void;
}

/** Maximum nesting depth. Each level is a separate query when expanded, and beyond a
 *  few levels the tree stops being readable. */
const MAX_LEVELS = 3;

export default function GroupDialog({
  open,
  columns,
  groupBy,
  kindByColumn,
  onApply,
  onClose,
}: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<string[]>(groupBy);

  useEffect(() => {
    if (open) setDraft(groupBy);
    // seeded on open only, so the draft survives while the dialog is in use
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

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

  // a column may only be grouped once, so each select offers what the others haven't taken
  function availableFor(index: number): string[] {
    const taken = new Set(draft.filter((_, i) => i !== index));
    return columns.filter((c) => !taken.has(c));
  }

  const firstFree = columns.find((c) => !draft.includes(c));

  return createPortal(
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal modal-sm" role="dialog" aria-modal="true" aria-label={t("group.title") ?? "Group"}>
        <header className="modal-head">
          <span className="modal-title">
            <IconColumns />
            {t("group.title")}
          </span>
          <button type="button" className="icon-btn" onClick={onClose} aria-label={t("filter.close")}>
            <IconClose />
          </button>
        </header>

        <div className="modal-body">
          {draft.length === 0 && <p className="muted filter-empty">{t("group.empty")}</p>}

          {draft.map((col, i) => (
            <div className="filter-row filter-row-dialog" key={i}>
              <span className="filter-conjunction">
                {i === 0 ? t("group.by") : t("group.then_by")}
              </span>
              <ColumnSelect
                columns={availableFor(i)}
                value={col}
                kindByColumn={kindByColumn}
                onChange={(next) =>
                  setDraft((prev) => prev.map((c, j) => (j === i ? next : c)))
                }
              />
              <button
                type="button"
                className="icon-btn danger"
                onClick={() => setDraft((prev) => prev.filter((_, j) => j !== i))}
                aria-label={t("cleaning.remove")}
                title={t("cleaning.remove") ?? ""}
              >
                <IconTrash />
              </button>
            </div>
          ))}

          <button
            type="button"
            className="link-btn"
            onClick={() => firstFree && setDraft([...draft, firstFree])}
            disabled={!firstFree || draft.length >= MAX_LEVELS}
          >
            <IconPlusCircle />
            {t("group.add")}
          </button>
        </div>

        <footer className="modal-foot">
          <button type="button" className="link-btn" onClick={() => setDraft([])} disabled={draft.length === 0}>
            <IconReset />
            {t("filter.reset")}
          </button>
          <span className="modal-foot-spacer" />
          <button type="button" className="btn secondary" onClick={onClose}>
            {t("filter.cancel")}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              onApply(draft);
              onClose();
            }}
          >
            {t("filter.apply")}
          </button>
        </footer>
      </div>
    </div>,
    document.body
  );
}
