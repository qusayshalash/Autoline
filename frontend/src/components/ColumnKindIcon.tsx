import type { ColumnKind } from "../api/client";

/** Per-column glyph shown at the start of every grid header (and in the column
 *  manager). The kind is inferred from the data by the backend, so a calendar only
 *  ever appears on a column whose values really are dates. */
export default function ColumnKindIcon({ kind }: { kind?: ColumnKind }) {
  const common = {
    width: 13,
    height: 13,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "col-kind",
    "aria-hidden": true,
  };

  if (kind === "date") {
    return (
      <svg {...common}>
        <rect x="2.5" y="3.5" width="11" height="10" rx="1.5" />
        <path d="M2.5 6.5h11M5.5 2v3M10.5 2v3" />
      </svg>
    );
  }
  if (kind === "number") {
    return (
      <svg {...common}>
        <path d="M6 2.5L4.5 13.5M11 2.5L9.5 13.5M2.5 5.5h11M2 10.5h11" />
      </svg>
    );
  }
  if (kind === "category") {
    return (
      <svg {...common}>
        <path d="M8.6 2.5H13.5V7.4a1 1 0 0 1-.3.7l-5.1 5.1a1 1 0 0 1-1.4 0L2.8 9.4a1 1 0 0 1 0-1.4l5.1-5.1a1 1 0 0 1 .7-.4z" />
        <circle cx="10.8" cy="5.2" r="0.9" />
      </svg>
    );
  }
  // text
  return (
    <svg {...common}>
      <path d="M3.5 4V3h9v1M8 3.2v9.6M6 13h4" />
    </svg>
  );
}
