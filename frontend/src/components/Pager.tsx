import { useState } from "react";

import { IconChevronLeft, IconChevronRight, IconFirst, IconLast } from "./SheetIcons";

/** Page numbers to show, with `null` marking an elided run.
 *  Always renders the first and last page plus a window around the current one, so the
 *  control keeps a stable width even at 41,000 pages. */
export function pageItems(current: number, total: number, window = 2): (number | null)[] {
  if (total <= 1) return [1];
  const pages = new Set<number>([1, total]);
  for (let p = current - window; p <= current + window; p++) {
    if (p >= 1 && p <= total) pages.add(p);
  }
  const sorted = [...pages].sort((a, b) => a - b);
  const out: (number | null)[] = [];
  let prev = 0;
  for (const p of sorted) {
    if (prev && p - prev > 1) out.push(null);
    out.push(p);
    prev = p;
  }
  return out;
}

interface Props {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
  labels: { first: string; prev: string; next: string; last: string; goTo: string };
}

export default function Pager({ page, totalPages, onChange, labels }: Props) {
  // free text while typing so the field can be cleared or partially typed ("30" on the
  // way to "3000") without the grid jumping on every keystroke
  const [draft, setDraft] = useState("");
  const editing = draft !== "";

  function commit() {
    const n = Number(draft);
    if (Number.isInteger(n) && n >= 1 && n <= totalPages) onChange(n);
    setDraft("");
  }

  return (
    <div className="pager">
      <button type="button" disabled={page <= 1} onClick={() => onChange(1)} aria-label={labels.first}>
        <IconFirst />
      </button>
      <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label={labels.prev}>
        <IconChevronLeft />
      </button>

      {pageItems(page, totalPages).map((p, i) =>
        p === null ? (
          <span key={`gap-${i}`} className="pager-gap">
            …
          </span>
        ) : (
          <button
            key={p}
            type="button"
            className={p === page ? "pager-page active" : "pager-page"}
            aria-current={p === page ? "page" : undefined}
            onClick={() => onChange(p)}
          >
            {p.toLocaleString()}
          </button>
        )
      )}

      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        aria-label={labels.next}
      >
        <IconChevronRight />
      </button>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onChange(totalPages)}
        aria-label={labels.last}
      >
        <IconLast />
      </button>

      {/* direct jump - the numbered buttons only reach a window around the current page,
          so there is no other way to get to page 3,000 of 41,145 */}
      <input
        type="number"
        className="pager-goto"
        min={1}
        max={totalPages}
        value={editing ? draft : page}
        aria-label={labels.goTo}
        title={labels.goTo}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setDraft("");
        }}
        onBlur={commit}
      />
    </div>
  );
}
