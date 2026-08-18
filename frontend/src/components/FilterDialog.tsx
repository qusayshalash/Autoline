import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { newFilter, type ColumnKind, type FilterRule } from "../api/client";
import { columnLabel } from "../data/columnDictionary";
import FilterBuilder from "./FilterBuilder";
import { IconClose, IconFilter, IconPlusCircle, IconReset, IconTrash } from "./SheetIcons";

interface Props {
  open: boolean;
  columns: string[];
  filters: FilterRule[];
  datasetId: string;
  source: "raw" | "cleaned";
  kindByColumn?: Map<string, ColumnKind>;
  onApply: (filters: FilterRule[]) => void;
  onClose: () => void;
}

export default function FilterDialog({
  open,
  columns,
  filters,
  datasetId,
  source,
  kindByColumn,
  onApply,
  onClose,
}: Props) {
  const { t, i18n } = useTranslation();
  // Edits live in a draft until Apply, so opening the dialog and closing it again -
  // or hitting Cancel - never touches the grid.
  const [draft, setDraft] = useState<FilterRule[]>(filters);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) setDraft(filters);
    // re-seeding only on open is deliberate: `filters` changing underneath an open
    // dialog (e.g. a value filter applied from a column menu) must not wipe the draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  // Value filters come from the column header menus ("filter by value"). They aren't
  // editable as a rule row, but they're listed here so every active filter is visible
  // and removable from one place.
  const rules = draft.filter((f) => f.op !== "in");
  const valueFilters = draft.filter((f) => f.op === "in");

  function setRules(next: FilterRule[]) {
    setDraft([...valueFilters, ...next]);
  }

  function removeValueFilter(column: string) {
    setDraft(draft.filter((f) => !(f.op === "in" && f.column === column)));
  }

  function apply() {
    // drop half-written rules rather than sending an empty match to the backend
    const usable = draft.filter(
      (f) => f.op === "in" || f.op === "is_null" || f.op === "not_null" || String(f.value ?? "") !== ""
    );
    onApply(usable);
    onClose();
  }

  return createPortal(
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={t("filter.title") ?? "Filter"}
        ref={panelRef}
      >
        <header className="modal-head">
          <span className="modal-title">
            <IconFilter />
            {t("filter.title")}
          </span>
          <button type="button" className="icon-btn" onClick={onClose} aria-label={t("filter.close")}>
            <IconClose />
          </button>
        </header>

        <div className="modal-body">
          {valueFilters.length > 0 && (
            <div className="filter-values-block">
              <div className="filter-values-title">{t("filter.value_filters")}</div>
              {valueFilters.map((f) => (
                <div className="filter-value-row" key={f.column}>
                  <strong>{columnLabel(f.column, i18n.language)}</strong>
                  <span className="muted">{t("filter.n_values", { count: f.values?.length ?? 0 })}</span>
                  <button
                    type="button"
                    className="icon-btn danger"
                    onClick={() => removeValueFilter(f.column)}
                    aria-label={t("cleaning.remove")}
                  >
                    <IconTrash />
                  </button>
                </div>
              ))}
            </div>
          )}

          {rules.length === 0 && valueFilters.length === 0 && (
            <p className="muted filter-empty">{t("filter.empty")}</p>
          )}

          <FilterBuilder
            columns={columns}
            filters={rules}
            onChange={setRules}
            hideAddButton
            variant="dialog"
            datasetId={datasetId}
            source={source}
            kindByColumn={kindByColumn}
          />

          <button
            type="button"
            className="link-btn"
            onClick={() => setRules([...rules, newFilter(columns)])}
            disabled={columns.length === 0}
          >
            <IconPlusCircle />
            {t("filter.add_rule")}
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
          <button type="button" className="btn" onClick={apply}>
            {t("filter.apply")}
          </button>
        </footer>
      </div>
    </div>,
    document.body
  );
}
