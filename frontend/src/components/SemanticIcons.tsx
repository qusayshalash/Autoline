/** Meaning-based column glyphs (a car for a model column, a tyre for a tyre column...).
 *  Used when a column is recognised in the column dictionary; columns that aren't
 *  recognised fall back to the data-type glyph in ColumnKindIcon. */

export type SemanticIconName =
  | "hash"
  | "factory"
  | "car"
  | "engine"
  | "tyre"
  | "fuel"
  | "calendar"
  | "palette"
  | "shield"
  | "key"
  | "barcode"
  | "star"
  | "road"
  | "doc"
  | "leaf";

const svg = {
  width: 14,
  height: 14,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.3,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className: "col-kind",
  "aria-hidden": true,
};

const PATHS: Record<SemanticIconName, React.ReactNode> = {
  hash: <path d="M6 2.5L4.5 13.5M11 2.5L9.5 13.5M2.5 5.5h11M2 10.5h11" />,
  factory: (
    <>
      <path d="M2 13.5V7l4 2.5V7l4 2.5V4h4v9.5z" />
      <path d="M1.5 13.5h13" />
    </>
  ),
  car: (
    <>
      <path d="M2 10.5V8l1.6-3.2A1 1 0 0 1 4.5 4.2h7a1 1 0 0 1 .9.6L14 8v2.5" />
      <path d="M2 10.5h12M3 8h10" />
      <circle cx="4.6" cy="11.6" r="1.2" />
      <circle cx="11.4" cy="11.6" r="1.2" />
    </>
  ),
  engine: (
    <>
      <path d="M2.5 6.5h2l1.5-2h4v2h2l1.5 1.5v3.5h-11z" />
      <path d="M5 4.5V3h4v1.5M13.5 8.5h1v2h-1" />
    </>
  ),
  tyre: (
    <>
      <circle cx="8" cy="8" r="5.8" />
      <circle cx="8" cy="8" r="2.3" />
      <path d="M8 2.2v3.5M8 10.3v3.5M2.2 8h3.5M10.3 8h3.5" />
    </>
  ),
  fuel: (
    <>
      <path d="M3 13.5V3.2a.7.7 0 0 1 .7-.7h4.6a.7.7 0 0 1 .7.7v10.3" />
      <path d="M2.2 13.5h7.6M3 7.5h6" />
      <path d="M9 5.5l2.4 1.6v4.4a1 1 0 0 0 2 0V7.4l-1.4-1.9" />
    </>
  ),
  calendar: (
    <>
      <rect x="2.5" y="3.5" width="11" height="10" rx="1.5" />
      <path d="M2.5 6.5h11M5.5 2v3M10.5 2v3" />
    </>
  ),
  palette: (
    <>
      <path d="M8 2a6 6 0 0 0 0 12c.9 0 1.4-.6 1.4-1.3 0-.8-.7-1.1-.7-1.9 0-.6.5-1 1.1-1H11a3 3 0 0 0 3-3C14 4.3 11.3 2 8 2z" />
      <circle cx="5.2" cy="6.4" r="0.8" />
      <circle cx="8" cy="5" r="0.8" />
      <circle cx="4.6" cy="9.5" r="0.8" />
    </>
  ),
  shield: <path d="M8 2l5 2v4.2c0 3-2.1 5.2-5 5.8-2.9-.6-5-2.8-5-5.8V4z" />,
  key: (
    <>
      <circle cx="5.5" cy="5.5" r="3" />
      <path d="M7.7 7.7l5.3 5.3M11 11l1.4-1.4M12.4 12.4l1.2-1.2" />
    </>
  ),
  barcode: <path d="M2.5 3v10M5 3v10M7 3v7M9 3v10M11.5 3v7M13.5 3v10" />,
  star: <path d="M8 2.3l1.8 3.7 4 .6-2.9 2.8.7 4-3.6-1.9-3.6 1.9.7-4L2.2 6.6l4-.6z" />,
  road: (
    <>
      <path d="M5 2.5L2.5 13.5M11 2.5l2.5 11" />
      <path d="M8 3v2M8 7v2M8 11v2" />
    </>
  ),
  doc: (
    <>
      <path d="M4 2.5h5l3 3v8H4z" />
      <path d="M9 2.5v3h3M6 8.5h4M6 10.5h4" />
    </>
  ),
  leaf: (
    <>
      <path d="M13 3c0 6-3.5 9-7 9a3.4 3.4 0 0 1-3-1.7C4.5 5.5 8 3.4 13 3z" />
      <path d="M3 13.5c1.5-3 3.7-5.2 6.5-6.5" />
    </>
  ),
};

export default function SemanticIcon({ name }: { name: SemanticIconName }) {
  return <svg {...svg}>{PATHS[name]}</svg>;
}
