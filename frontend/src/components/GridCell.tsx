import type { ColumnKind } from "../api/client";

/** Number of chip colours available. Values are mapped onto them by hash, so the same
 *  value always gets the same colour within and across sessions - no per-dataset
 *  configuration and no assumptions about what the values mean. */
const CHIP_COLOURS = 8;

function chipIndex(value: string): number {
  // FNV-1a: cheap, stable, and spreads short similar strings well
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return Math.abs(h) % CHIP_COLOURS;
}

interface Props {
  value: string;
  kind?: ColumnKind;
}

export default function GridCell({ value, kind }: Props) {
  if (value === "") return <span className="cell-empty">–</span>;
  if (kind === "category") {
    return <span className={`chip chip-${chipIndex(value)}`}>{value}</span>;
  }
  return <>{value}</>;
}
