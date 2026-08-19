import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { fetchDistinctValues } from "../api/client";

interface Props {
  datasetId: string;
  source: "raw" | "cleaned";
  column: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

const SUGGESTION_LIMIT = 50;

/** Free-text input that also suggests the values actually present in the column, so a
 *  filter can be built by picking rather than typing (and without guessing at spelling
 *  or at how a value is capitalised in the source file). */
export default function ValueAutocomplete({
  datasetId,
  source,
  column,
  value,
  onChange,
  placeholder,
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState(value);
  const [highlight, setHighlight] = useState(-1);
  const [pos, setPos] = useState<{ left: number; top: number; width: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const suppressNextFocus = useRef(false);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), 250);
    return () => clearTimeout(id);
  }, [value]);

  const { data, isFetching, isError } = useQuery({
    queryKey: ["distinct-values", datasetId, source, column, debounced, "suggest"],
    queryFn: () =>
      fetchDistinctValues(datasetId, {
        column,
        source,
        search: debounced,
        limit: SUGGESTION_LIMIT,
      }),
    enabled: open && !!column,
  });

  const items = data?.values ?? [];

  function place() {
    const r = inputRef.current?.getBoundingClientRect();
    if (!r) return;
    const MAX_H = 260;
    const spaceBelow = window.innerHeight - r.bottom - 8;
    const top = spaceBelow < MAX_H && r.top > spaceBelow ? Math.max(8, r.top - 4 - MAX_H) : r.bottom + 4;
    setPos({ left: r.left, top, width: r.width });
  }

  function openList() {
    if (suppressNextFocus.current) {
      suppressNextFocus.current = false;
      return;
    }
    place();
    setHighlight(-1);
    setOpen(true);
  }

  useEffect(() => {
    if (!open) return;
    function onDocDown(e: MouseEvent) {
      const target = e.target as Node;
      if (inputRef.current?.contains(target) || listRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onScrollOrResize(e: Event) {
      // scrolling inside the suggestion list itself must not dismiss it
      if (e.target instanceof Node && listRef.current?.contains(e.target)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", onDocDown);
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      document.removeEventListener("mousedown", onDocDown);
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open]);

  function choose(v: string) {
    onChange(v);
    setOpen(false);
    // returning focus to the input would otherwise re-trigger onFocus and immediately
    // reopen the list the user just dismissed by picking a value
    suppressNextFocus.current = true;
    inputRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return openList();
      const dir = e.key === "ArrowDown" ? 1 : -1;
      setHighlight((h) => Math.min(items.length - 1, Math.max(0, h + dir)));
      return;
    }
    if (e.key === "Enter" && open && highlight >= 0 && items[highlight]) {
      e.preventDefault();
      choose(items[highlight].value);
      return;
    }
    if (e.key === "Escape" && open) {
      // close only the suggestions - the surrounding dialog must stay open
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="text"
        className="autocomplete-input"
        placeholder={placeholder}
        value={value}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        onChange={(e) => {
          onChange(e.target.value);
          if (!open) openList();
          else place();
        }}
        onFocus={openList}
        onKeyDown={onKeyDown}
      />
      {open &&
        pos &&
        createPortal(
          <div
            className="autocomplete-list"
            ref={listRef}
            style={{ position: "fixed", left: pos.left, top: pos.top, minWidth: pos.width }}
          >
            {isFetching ? (
              <div className="muted autocomplete-note">{t("common.loading")}</div>
            ) : isError ? (
              /* "no values found" would be a claim about the data; the lookup simply
                 failed, and the difference matters when the user is deciding whether
                 the value they typed exists */
              <div className="muted autocomplete-note">{t("common.error_loading_data")}</div>
            ) : items.length === 0 ? (
              <div className="muted autocomplete-note">{t("column_menu.no_values_found")}</div>
            ) : (
              items.map((it, i) => (
                <button
                  type="button"
                  key={it.value}
                  className={i === highlight ? "autocomplete-item active" : "autocomplete-item"}
                  onMouseEnter={() => setHighlight(i)}
                  onClick={() => choose(it.value)}
                >
                  <span className="autocomplete-value">{it.value}</span>
                  <span className="autocomplete-count">{it.count.toLocaleString()}</span>
                </button>
              ))
            )}
          </div>,
          document.body
        )}
    </>
  );
}
