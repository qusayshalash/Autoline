import { useTranslation } from "react-i18next";

/**
 * A row with a cell somebody corrected by hand, marked beside the row number.
 *
 * The cell itself already says so, with its dotted outline and the value the file had -
 * but only to somebody looking at that cell, and a wide table hides most of its cells
 * off-screen. This is the same fact at the one place every row shows: whether the row
 * has been touched, and how many of its cells.
 *
 * Kept apart from the batch marks (+ and the turning arrow) on purpose. Those say a file
 * brought a new version of the whole record; this says a person changed part of it, and
 * that part can still be put back.
 */
export default function CorrectionMark({ count }: { count: number }) {
  const { t } = useTranslation();
  const label = t("corrections.row", { count });

  return (
    <span className="correction-mark" title={label}>
      <span className="correction-pen" aria-hidden="true">
        {/* drawn, not the ✎ character: a font's glyph sits at its own size and baseline,
            and beside the drawn batch marks it would be the one that looks off */}
        <svg
          width={11}
          height={11}
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.6}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M7.9 2.1l2 2L4.2 9.8 1.8 10.2l.4-2.4z" />
          <path d="M6.9 3.1l2 2" />
        </svg>
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
