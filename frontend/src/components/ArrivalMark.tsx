import { useTranslation } from "react-i18next";

import type { Arrival } from "../api/client";
import { formatDate } from "../data/datetime";

/**
 * A record a recent batch brought, marked in the grid.
 *
 * Two channels, not one. Colour alone excludes anybody who cannot separate these two
 * hues, and a dot alone says "something" without saying what - so the mark carries a
 * shape as well as a colour, and an accessible name that reads as a sentence rather
 * than as a word. The shapes are symbols, not letters, so they sit beside the ✎ of a
 * hand correction as one family and read the same in every language: a plus for a
 * record that was added, a turning arrow for one that was replaced.
 *
 * New and updated are kept apart because they answer different questions: which vehicles
 * we now have that we did not, and which of the ones we had have changed.
 */
export default function ArrivalMark({
  kind,
  when,
}: {
  kind: Arrival;
  /** when the batch landed; the same for every row of it */
  when?: string | null;
}) {
  const { t, i18n } = useTranslation();
  const date = when ? formatDate(when, i18n.language) : "";
  const label = t(kind === "new" ? "arrivals.new_at" : "arrivals.updated_at", {
    when: date,
  });

  return (
    <span className={`arrival-mark ${kind}`} title={label}>
      <span className="arrival-dot" aria-hidden="true">
        {kind === "new" ? <IconAdded /> : <IconReplaced />}
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}

const glyph = {
  width: 11,
  height: 11,
  viewBox: "0 0 12 12",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function IconAdded() {
  return (
    <svg {...glyph}>
      <path d="M6 2.5v7M2.5 6h7" />
    </svg>
  );
}

function IconReplaced() {
  return (
    <svg {...glyph}>
      <path d="M9.6 4.4A4 4 0 1 0 10 7" />
      <path d="M10 1.8v2.8H7.2" />
    </svg>
  );
}
