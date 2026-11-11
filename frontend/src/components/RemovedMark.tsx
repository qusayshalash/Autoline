import { useTranslation } from "react-i18next";

/**
 * A record the government registry no longer lists - scrapped, exported, off the road.
 *
 * Kept, not deleted, so it can still be looked up; this says it is gone. One of the
 * batch marks' family: the same round badge, a drawn glyph rather than a letter (a
 * circle struck through), and red for a vehicle that has left, set apart from the
 * green of one that arrived and the amber of one that changed.
 */
export default function RemovedMark() {
  const { t } = useTranslation();
  const label = t("registry.removed_mark");
  return (
    <span className="arrival-mark removed" title={label}>
      <span className="arrival-dot removed" aria-hidden="true">
        <svg
          width={11}
          height={11}
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
        >
          <circle cx="6" cy="6" r="4" />
          <path d="M3.2 8.8l5.6-5.6" />
        </svg>
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
