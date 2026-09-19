import { useTranslation } from "react-i18next";

import type { Arrival } from "../api/client";
import { formatDate } from "../data/datetime";

/**
 * A record a recent batch brought, marked in the grid.
 *
 * Two channels, not one. Colour alone excludes anybody who cannot separate these two
 * hues, and a dot alone says "something" without saying what - so the mark carries a
 * visible letter as well as a colour, and an accessible name that reads as a sentence
 * rather than as a word.
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
        {t(`arrivals.${kind}`).slice(0, 1)}
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
