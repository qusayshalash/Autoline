import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import type { ColumnKind } from "../api/client";
import { columnLabel, columnMeta, usesRawHeaders } from "../data/columnDictionary";
import ColumnKindIcon from "./ColumnKindIcon";
import SemanticIcon from "./SemanticIcons";

interface Props {
  columns: string[];
  value: string;
  onChange: (column: string) => void;
  kindByColumn?: Map<string, ColumnKind>;
  placeholder?: string;
}

/** Column picker that opens straight into a searchable list showing each column's icon
 *  and label - a native <select> can show neither, and becomes unusable once a file has
 *  dozens of columns. */
export default function ColumnSelect({ columns, value, onChange, kindByColumn, placeholder }: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [pos, setPos] = useState<{ left: number; top: number; width: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return columns;
    // match the raw header as well as the localised label, so either works
    return columns.filter(
      (c) =>
        c.toLowerCase().includes(q) || columnLabel(c, i18n.language).toLowerCase().includes(q)
    );
  }, [columns, search, i18n.language]);

  function openPanel() {
    const r = triggerRef.current?.getBoundingClientRect();
    if (!r) return;
    const MAX_H = 300;
    const spaceBelow = window.innerHeight - r.bottom - 8;
    const top = spaceBelow < MAX_H && r.top > spaceBelow ? Math.max(8, r.top - 4 - MAX_H) : r.bottom + 4;
    setPos({ left: r.left, top, width: Math.max(r.width, 220) });
    setSearch("");
    setHighlight(Math.max(0, columns.indexOf(value)));
    setOpen(true);
    // focus lands on the search box so typing filters immediately
    setTimeout(() => searchRef.current?.focus(), 0);
  }

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onScroll(e: Event) {
      if (e.target instanceof Node && panelRef.current?.contains(e.target)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open]);

  function choose(c: string) {
    onChange(c);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const dir = e.key === "ArrowDown" ? 1 : -1;
      setHighlight((h) => Math.min(matches.length - 1, Math.max(0, h + dir)));
      return;
    }
    if (e.key === "Enter" && matches[highlight]) {
      e.preventDefault();
      choose(matches[highlight]);
      return;
    }
    if (e.key === "Escape") {
      // close the picker only - never the dialog hosting it
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
    }
  }

  function iconFor(c: string) {
    const meta = usesRawHeaders(i18n.language) ? undefined : columnMeta(c);
    return meta ? <SemanticIcon name={meta.icon} /> : <ColumnKindIcon kind={kindByColumn?.get(c)} />;
  }

  return (
    <>
      <button
        type="button"
        ref={triggerRef}
        className="column-select"
        onClick={() => (open ? setOpen(false) : openPanel())}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={value || undefined}
      >
        {value ? iconFor(value) : null}
        <span className="column-select-label">
          {value ? columnLabel(value, i18n.language) : placeholder ?? t("group.pick_column")}
        </span>
        <svg className={open ? "column-select-caret open" : "column-select-caret"} width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M2 3.5L5 7l3-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open &&
        pos &&
        createPortal(
          <div
            className="column-select-panel"
            ref={panelRef}
            role="listbox"
            style={{ position: "fixed", left: pos.left, top: pos.top, width: pos.width }}
          >
            <input
              ref={searchRef}
              type="search"
              value={search}
              placeholder={placeholder ?? t("group.pick_column") ?? ""}
              onChange={(e) => {
                setSearch(e.target.value);
                setHighlight(0);
              }}
              onKeyDown={onKeyDown}
            />
            <div className="column-select-list">
              {matches.length === 0 ? (
                <div className="muted autocomplete-note">{t("column_menu.no_values_found")}</div>
              ) : (
                matches.map((c, i) => (
                  <button
                    type="button"
                    key={c}
                    role="option"
                    aria-selected={c === value}
                    className={`column-select-option${i === highlight ? " active" : ""}${
                      c === value ? " selected" : ""
                    }`}
                    onMouseEnter={() => setHighlight(i)}
                    onClick={() => choose(c)}
                    title={c}
                  >
                    {iconFor(c)}
                    <span className="column-select-option-label">{columnLabel(c, i18n.language)}</span>
                  </button>
                ))
              )}
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
