import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { fetchDistinctValues, type ColumnKind, type FilterRule } from "../api/client";
import { columnLabel, columnMeta, usesRawHeaders } from "../data/columnDictionary";
import ColumnKindIcon from "./ColumnKindIcon";
import SemanticIcon from "./SemanticIcons";

interface Props {
  column: string;
  kind?: ColumnKind;
  datasetId: string;
  source: "raw" | "cleaned";
  sortBy: string | null;
  sortDir: "asc" | "desc";
  onSort: (column: string, dir: "asc" | "desc") => void;
  filters: FilterRule[];
  onFiltersChange: (filters: FilterRule[]) => void;
  onHide: () => void;
  canDelete: boolean;
  onDeleteColumn: () => void;
  /** true when this column's values contain Hebrew and a translation is available */
  canTranslate: boolean;
  translated: boolean;
  onToggleTranslate: () => void;
}

export default function ColumnHeaderMenu({
  column,
  kind,
  datasetId,
  source,
  sortBy,
  sortDir,
  onSort,
  filters,
  onFiltersChange,
  onHide,
  canDelete,
  onDeleteColumn,
  canTranslate,
  translated,
  onToggleTranslate,
}: Props) {
  const { t, i18n } = useTranslation();
  // in raw-header mode the column keeps its file name and its data-type glyph, with no
  // meaning-based icon layered on top
  const meta = usesRawHeaders(i18n.language) ? undefined : columnMeta(column);
  const label = columnLabel(column, i18n.language);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [panelPos, setPanelPos] = useState<{ left: number; top: number; maxHeight: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const existingFilter = filters.find((f) => f.column === column && f.op === "in");

  function openMenu() {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      const PANEL_WIDTH = 260;
      // the values list absorbs whatever this leaves over, so a taller panel simply
      // shows more values at once; it is clamped to the viewport just below
      const PREFERRED_HEIGHT = 560;
      const GAP = 4;
      const EDGE = 8;

      // clamp so the (fixed-width) panel doesn't overflow the right/left edge of the viewport
      const left = Math.min(Math.max(rect.left, EDGE), window.innerWidth - PANEL_WIDTH - EDGE);

      // Neither side is guaranteed to fit the panel, so pick the roomier one and cap the
      // panel's height to what's actually available there - flipping without capping used
      // to push the panel off the top of the viewport on short screens.
      const height = Math.min(PREFERRED_HEIGHT, window.innerHeight - 2 * EDGE);
      const spaceBelow = window.innerHeight - rect.bottom - GAP - EDGE;
      const spaceAbove = rect.top - GAP - EDGE;

      let top: number;
      if (spaceBelow >= height) {
        top = rect.bottom + GAP;
      } else if (spaceAbove >= height) {
        top = rect.top - GAP - height;
      } else {
        // neither side can hold the panel (short viewport): pin it inside the viewport
        // rather than anchoring to the trigger, which would push it off-screen
        top = EDGE;
      }
      setPanelPos({ top, left, maxHeight: height });
    }
    setSearch("");
    setDebouncedSearch("");
    setSelected(new Set(existingFilter?.values ?? []));
    setOpen(true);
  }

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    if (!open) return;
    function onOutsideClick(e: MouseEvent) {
      const target = e.target as Node;
      if (
        triggerRef.current &&
        !triggerRef.current.contains(target) &&
        panelRef.current &&
        !panelRef.current.contains(target)
      ) {
        setOpen(false);
      }
    }
    function onResize() {
      setOpen(false);
    }
    function onScroll(e: Event) {
      // ignore scrolling inside the panel itself (e.g. the values list, or the panel's
      // own overflow when it's capped to viewport height) - only close when the page/table
      // behind it scrolls, since that would leave the fixed-position panel detached from
      // its trigger button.
      const target = e.target as Node;
      if (panelRef.current && panelRef.current.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", onOutsideClick);
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", onOutsideClick);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  const {
    data: distinct,
    isFetching,
    isError: distinctError,
  } = useQuery({
    queryKey: ["distinct-values", datasetId, source, column, debouncedSearch],
    queryFn: () => fetchDistinctValues(datasetId, { column, source, search: debouncedSearch, limit: 500 }),
    enabled: open,
  });

  const values = distinct?.values ?? [];
  const allVisibleSelected = values.length > 0 && values.every((v) => selected.has(v.value));

  function toggleValue(v: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(v)) next.delete(v);
      else next.add(v);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelected((prev) => {
      if (allVisibleSelected) {
        const next = new Set(prev);
        values.forEach((v) => next.delete(v.value));
        return next;
      }
      return new Set([...prev, ...values.map((v) => v.value)]);
    });
  }

  function applyFilter() {
    const others = filters.filter((f) => !(f.column === column && f.op === "in"));
    if (selected.size > 0) {
      onFiltersChange([...others, { column, op: "in", values: Array.from(selected) }]);
    } else {
      onFiltersChange(others);
    }
    setOpen(false);
  }

  return (
    <div className="column-menu">
      {meta ? <SemanticIcon name={meta.icon} /> : <ColumnKindIcon kind={kind} />}
      {/* clicking the label sorts (and re-clicking flips direction), which is what
          people expect from a grid header; the funnel opens the full menu.
          The tooltip keeps the raw header visible - the label is presentation only. */}
      <button
        type="button"
        className="column-menu-name"
        title={column}
        onClick={() => onSort(column, sortBy === column && sortDir === "asc" ? "desc" : "asc")}
      >
        {label}
      </button>
      {sortBy === column && (
        <svg
          className="sort-icon active"
          width="11"
          height="11"
          viewBox="0 0 10 10"
          style={sortDir === "asc" ? { transform: "rotate(180deg)" } : undefined}
          aria-hidden="true"
        >
          <path d="M2 3.5L5 7l3-3.5" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      <button
        type="button"
        ref={triggerRef}
        className="column-menu-trigger"
        onClick={() => (open ? setOpen(false) : openMenu())}
        aria-label={label}
      >
        <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M2.5 3.5h11l-4.2 5v4l-2.6 1.2V8.5z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
        {existingFilter && <span className="column-menu-filter-dot" />}
      </button>

      {open &&
        panelPos &&
        createPortal(
          <div
            className="column-menu-panel"
            ref={panelRef}
            style={{
              position: "fixed",
              top: panelPos.top,
              left: panelPos.left,
              maxHeight: panelPos.maxHeight,
            }}
          >
            <button type="button" onClick={() => { onSort(column, "asc"); setOpen(false); }}>
              {t("column_menu.sort_asc")}
            </button>
            <button type="button" onClick={() => { onSort(column, "desc"); setOpen(false); }}>
              {t("column_menu.sort_desc")}
            </button>
            <hr />
            {/* offered only on columns that actually hold Hebrew text */}
            {canTranslate && (
              <button type="button" onClick={() => { onToggleTranslate(); setOpen(false); }}>
                {translated ? t("column_menu.show_original") : t("column_menu.translate_values")}
              </button>
            )}
            <button type="button" onClick={() => { onHide(); setOpen(false); }}>
              {t("column_menu.hide")}
            </button>
            {canDelete && (
              <button type="button" className="column-menu-danger" onClick={() => { onDeleteColumn(); setOpen(false); }}>
                {t("column_menu.delete")}
              </button>
            )}
            <hr />
            <div className="column-menu-filter">
              <div className="column-menu-filter-title">{t("column_menu.filter_by")}</div>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("column_menu.search_values") ?? ""}
                autoFocus
              />
              <label className="column-menu-value-row">
                <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAll} />
                {t("column_menu.select_all")}
              </label>
              <div className="column-menu-values-list">
                {isFetching ? (
                  <div className="muted">{t("common.loading")}</div>
                ) : distinctError ? (
                  <div style={{ color: "var(--danger)" }}>{t("common.error_loading_data")}</div>
                ) : values.length === 0 ? (
                  <div className="muted">{t("column_menu.no_values_found")}</div>
                ) : (
                  values.map((v) => (
                    <label className="column-menu-value-row" key={v.value}>
                      <input type="checkbox" checked={selected.has(v.value)} onChange={() => toggleValue(v.value)} />
                      <span className="column-menu-value-text" title={v.value}>{v.value}</span>
                      <span className="column-menu-value-count">{v.count.toLocaleString()}</span>
                    </label>
                  ))
                )}
              </div>
              {distinct?.truncated && (
                <div className="muted" style={{ fontSize: "0.75rem" }}>
                  {t("column_menu.showing_x_of_y", { shown: values.length, total: distinct.total_distinct })}
                </div>
              )}
              <div className="column-menu-filter-actions">
                <button type="button" className="btn secondary" onClick={() => setOpen(false)}>
                  {t("column_menu.cancel")}
                </button>
                <button type="button" className="btn" onClick={applyFilter}>
                  {t("column_menu.apply")}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
