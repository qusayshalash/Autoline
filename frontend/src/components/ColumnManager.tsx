import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import type { ColumnKind } from "../api/client";
import { columnLabel, columnMeta, usesRawHeaders } from "../data/columnDictionary";
import { anchoredPosition, type AnchoredPosition } from "../utils/anchorPosition";
import ColumnKindIcon from "./ColumnKindIcon";
import SemanticIcon from "./SemanticIcons";

const PANEL_WIDTH = 320;
const PANEL_HEIGHT = 460;

interface Props {
  open: boolean;
  onClose: () => void;
  /** the toolbar button the panel hangs off */
  anchorRef: React.RefObject<HTMLElement | null>;
  columns: string[];
  hidden: Set<string>;
  kindByColumn: Map<string, ColumnKind>;
  onToggle: (column: string) => void;
  onSetHidden: (hidden: Set<string>) => void;
  showRowNumbers: boolean;
  onToggleRowNumbers: () => void;
  canDelete: boolean;
  onDeleteHidden: () => void;
}

export default function ColumnManager({
  open,
  onClose,
  anchorRef,
  columns,
  hidden,
  kindByColumn,
  onToggle,
  onSetHidden,
  showRowNumbers,
  onToggleRowNumbers,
  canDelete,
  onDeleteHidden,
}: Props) {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState("");
  const [pos, setPos] = useState<AnchoredPosition | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const rect = anchorRef.current?.getBoundingClientRect();
    if (rect) {
      setPos(anchoredPosition(rect, { width: PANEL_WIDTH, preferredHeight: PANEL_HEIGHT }));
    }
    setSearch("");
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const target = e.target as Node;
      if (anchorRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    function onScroll(e: Event) {
      // scrolling the column list itself must not dismiss the panel
      if (e.target instanceof Node && panelRef.current?.contains(e.target)) return;
      onClose();
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onClose);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onClose);
    };
  }, [open, onClose, anchorRef]);

  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return columns;
    return columns.filter(
      (c) => c.toLowerCase().includes(q) || columnLabel(c, i18n.language).toLowerCase().includes(q)
    );
  }, [columns, search, i18n.language]);

  if (!open || !pos) return null;

  const visibleCount = columns.length - hidden.size;
  const allShown = hidden.size === 0;

  return createPortal(
    <div
      className="column-manager"
      ref={panelRef}
      style={{ position: "fixed", left: pos.left, top: pos.top, width: PANEL_WIDTH, maxHeight: pos.maxHeight }}
    >
      <div className="column-manager-head">
        <strong>{t("sheet.manage_columns")}</strong>
        <span className="muted">
          {visibleCount}/{columns.length}
        </span>
      </div>

      <input
        type="search"
        className="column-manager-search"
        placeholder={t("sheet.search_columns") ?? ""}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        autoFocus
      />

      <label className="column-manager-row column-manager-all">
        <input
          type="checkbox"
          checked={allShown}
          // unchecking would leave the grid with no columns at all, so it only ever
          // restores everything; hide individual columns from the rows below
          onChange={() => onSetHidden(allShown ? new Set(columns.slice(1)) : new Set())}
        />
        <span className="column-manager-label">{t("sheet.select_all_columns")}</span>
      </label>

      <div className="column-manager-list">
        {/* the ordinal column is a grid affordance rather than data, but it is still
            something the user may want out of the way */}
        {!search && (
          <label className="column-manager-row">
            <input type="checkbox" checked={showRowNumbers} onChange={onToggleRowNumbers} />
            <span className="col-kind-text">#</span>
            <span className="column-manager-label">{t("sheet.row_numbers")}</span>
          </label>
        )}

        {matches.length === 0 ? (
          <div className="muted autocomplete-note">{t("column_menu.no_values_found")}</div>
        ) : (
          matches.map((c) => {
            const meta = usesRawHeaders(i18n.language) ? undefined : columnMeta(c);
            return (
              <label className="column-manager-row" key={c} title={c}>
                <input type="checkbox" checked={!hidden.has(c)} onChange={() => onToggle(c)} />
                {meta ? <SemanticIcon name={meta.icon} /> : <ColumnKindIcon kind={kindByColumn.get(c)} />}
                <span className="column-manager-label">{columnLabel(c, i18n.language)}</span>
              </label>
            );
          })
        )}
      </div>

      <div className="column-manager-foot">
        <button type="button" className="link-btn" onClick={() => onSetHidden(new Set())} disabled={allShown}>
          {t("sheet.show_all")}
        </button>
        {canDelete && (
          <button
            type="button"
            className="link-btn danger"
            onClick={onDeleteHidden}
            disabled={hidden.size === 0}
          >
            {t("sheet.delete_hidden", { count: hidden.size })}
          </button>
        )}
      </div>
    </div>,
    document.body
  );
}
