import type { TFunction } from "i18next";

import type { BreakdownItem } from "../../api/statistics";
import { translateValue } from "../../data/valueDictionary";

/**
 * How one bucket is written out.
 *
 * The two structural buckets get their own words, since "" and "everything else" are not
 * values and must not be mistaken for one. Real values are translated only when the user
 * asked for it, and `translateValue` returns the original whenever it cannot render the
 * whole value - a half-translated category label is worse than an untranslated one.
 */
export function bucketLabel(
  item: Pick<BreakdownItem, "value" | "unspecified" | "other">,
  t: TFunction,
  language: string,
  translate: boolean
): string {
  if (item.unspecified) return t("statistics.unspecified");
  if (item.other) return t("statistics.other");
  return translate ? translateValue(item.value, language) : item.value;
}

/** Percentages are shown to one decimal: two is noise at this scale, none hides the
 *  difference between a 0.4% category and an empty one. */
export function formatPercent(value: number, language: string): string {
  return `${value.toLocaleString(language, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;
}

export function formatCount(value: number, language: string): string {
  return value.toLocaleString(language);
}

/** Milliseconds as a figure people read at a glance: 84 ms, or 1.24 s once it's slow
 *  enough that seconds are the natural unit. */
export function formatDuration(ms: number, language: string): string {
  if (ms < 1000) return `${Math.round(ms).toLocaleString(language)} ms`;
  return `${(ms / 1000).toLocaleString(language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} s`;
}
