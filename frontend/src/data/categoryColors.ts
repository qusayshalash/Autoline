/**
 * Colours for breakdown categories.
 *
 * Two rules, in order:
 *
 * 1. Values with a meaning get a fixed colour, so petrol is the same amber in every
 *    chart on every screen and electric never borrows the colour diesel had a moment
 *    ago. Fuel types and ownership are covered because those are the breakdowns this
 *    dashboard is built around.
 * 2. Everything else takes a colour from a shared palette by position. The backend
 *    orders buckets deterministically, so the same query always paints the same.
 *
 * The two structural buckets are deliberately colourless: "unspecified" and "other" are
 * absences of data, not categories, and giving them a hue would make them read as one.
 */

/** Chosen for separation at small sizes and for staying distinguishable side by side. */
export const PALETTE = [
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#14b8a6",
  "#ec4899",
  "#84cc16",
  "#f97316",
  "#06b6d4",
  "#a855f7",
  "#22c55e",
  "#eab308",
  "#f43f5e",
  "#3b82f6",
];

export const UNSPECIFIED_COLOR = "#9ca3af";
export const OTHER_COLOR = "#cbd5e1";

/** Stored values whose colour is fixed by what they mean, not by where they rank. */
const SEMANTIC: Record<string, string> = {
  // fuel type (sug_delek_nm) - the registry stores these in Hebrew
  'בנזין': "#f59e0b", // petrol
  'דיזל': "#64748b", // diesel
  'חשמל': "#10b981", // electric
  'חשמל/בנזין': "#06b6d4", // hybrid
  'חשמל/דיזל': "#0284c7", // diesel hybrid
  'גפמ"': "#a855f7", // LPG

  // ownership (baalut)
  'פרטי': "#4f46e5",
  'ליסינג': "#0ea5e9",
  'חברה': "#8b5cf6",
  'סוחר': "#f59e0b",
  'השכרה': "#14b8a6",
};

export interface ColourableItem {
  value: string;
  unspecified?: boolean;
  other?: boolean;
}

/** The colour for one bucket, given its position among the buckets shown. */
export function colorFor(item: ColourableItem, index: number): string {
  if (item.unspecified) return UNSPECIFIED_COLOR;
  if (item.other) return OTHER_COLOR;
  return SEMANTIC[item.value.trim()] ?? PALETTE[index % PALETTE.length];
}

/** Colours for a whole breakdown. Semantic values keep their colour and never consume a
 *  palette slot, so the remaining categories still get well-separated hues. */
export function colorsFor(items: ColourableItem[]): string[] {
  let next = 0;
  return items.map((item) => {
    if (item.unspecified) return UNSPECIFIED_COLOR;
    if (item.other) return OTHER_COLOR;
    const fixed = SEMANTIC[item.value.trim()];
    if (fixed) return fixed;
    return PALETTE[next++ % PALETTE.length];
  });
}
