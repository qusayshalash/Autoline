import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { columnLabel } from "../data/columnDictionary";
import { anchoredPosition } from "../utils/anchorPosition";

interface Props {
  columns: string[];
  /** empty means every column, which is the default and the old behaviour */
  selected: string[];
  onChange: (columns: string[]) => void;
}

/**
 * Which columns the free-text search looks in.
 *
 * Searching every column is what somebody expects the first time, and it is what this
 * does until told otherwise - a search that quietly declines to look somewhere returns
 * nothing and gives no reason for it. But every column is another pass over every row,
 * and on the registry that is the difference between 741ms and 53ms: most of the twenty-
 * two columns are internal codes and chassis numbers that nobody searches by name.
 *
 * So the control states the cost rather than hiding it. "Searching 22 of 22 columns" is
 * a sentence that invites the question it is the answer to.
 */
export default function SearchScope({ columns, selected, onChange }: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ left: 0, top: 0, maxHeight: 320 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const all = selected.length === 0;
  const count = all ? columns.length : selected.length;

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const target = e.target as Node;
      if (popoverRef.current?.contains(target) || buttonRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle(column: string) {
    // an empty selection means "all", so the first tick has to start from the full list
    // rather than from nothing - otherwise unticking one column would leave one ticked
    const base = all ? columns : selected;
    const next = base.includes(column)
      ? base.filter((c) => c !== column)
      : [...base, column];
    // back to every column: store it as empty, which is the same state the page starts in
    onChange(next.length === columns.length ? [] : next);
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className={all ? "search-scope" : "search-scope is-narrowed"}
        onClick={() => {
          if (buttonRef.current) {
            setPos(
              anchoredPosition(buttonRef.current.getBoundingClientRect(), {
                width: 260,
                preferredHeight: 360,
              })
            );
          }
          setOpen((o) => !o);
        }}
        aria-expanded={open}
        title={t("explorer.search_scope_hint") ?? ""}
      >
        {t("explorer.search_scope", { count, total: columns.length })}
      </button>

      {open && (
        <div
          ref={popoverRef}
          className="search-scope-popover"
          style={{
            position: "fixed",
            left: pos.left,
            top: pos.top,
            maxHeight: pos.maxHeight,
          }}
          role="dialog"
        >
          <p className="search-scope-note">{t("explorer.search_scope_hint")}</p>
          <div className="search-scope-actions">
            <button type="button" className="linkish" onClick={() => onChange([])}>
              {t("explorer.search_scope_all")}
            </button>
          </div>
          <ul>
            {columns.map((c) => {
              const on = all || selected.includes(c);
              return (
                <li key={c}>
                  <label>
                    <input type="checkbox" checked={on} onChange={() => toggle(c)} />
                    <span>{columnLabel(c, i18n.language)}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </>
  );
}
