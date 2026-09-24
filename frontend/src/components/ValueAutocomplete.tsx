import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { fetchGroups, type FilterRule } from "../api/client";
import { translateValue } from "../data/valueDictionary";

interface Props {
  datasetId: string;
  source: "raw" | "cleaned";
  column: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** The conditions already written, so the values offered are ones that still exist
   *  under them. Building "make = KIA and engine = ..." should not offer the engines of
   *  every other make, because picking one of those returns nothing. The caller leaves
   *  out this rule's own column, or the list could only ever offer back what is in the
   *  box already. */
  context?: FilterRule[];
  /** the grid's free-text search, which is also part of what is on screen */
  search?: string | null;
  searchColumns?: string[];
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
  context,
  search,
  searchColumns,
}: Props) {
  const { t, i18n } = useTranslation();
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
    queryKey: [
      "distinct-values",
      datasetId,
      source,
      column,
      debounced,
      search ?? "",
      JSON.stringify(context ?? []),
      "suggest",
    ],
    queryFn: () =>
      fetchGroups(datasetId, {
        column,
        source,
        page_size: SUGGESTION_LIMIT,
        value_search: debounced || null,
        search: search || null,
        search_columns: searchColumns,
        filters: context ?? [],
      }),
    enabled: open && !!column,
  });

  // Blank and missing are not values to pick; the operator list has is_null for those.
  const items = (data?.groups ?? []).filter(
    (v): v is { value: string; count: number } => !!v.value
  );

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
                  <SuggestedValue value={it.value} language={i18n.language} />
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

/**
 * One suggested value, translated where the dictionary can read it - with the stored
 * value kept beside it rather than replaced by it.
 *
 * Showing only the translation would be a lie about what is in the column: the filter
 * this builds compares against the Hebrew, so the Hebrew is what the reader is choosing.
 * Showing both is also how somebody learns the pair, which is worth more here than in
 * the grid, where the same treatment would double the width of every cell.
 */
function SuggestedValue({ value, language }: { value: string; language: string }) {
  const translated = translateValue(value, language);
  if (translated === value) return <span className="autocomplete-value">{value}</span>;
  return (
    <span className="autocomplete-value">
      {translated}
      <span className="autocomplete-original">{value}</span>
    </span>
  );
}
