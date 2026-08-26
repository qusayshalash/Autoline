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

/**
 * An aggregate over a measure column.
 *
 * Whole numbers print whole - a minimum, a maximum, or a sum that happens to land on an
 * integer is a value out of the file, and "2018.00" claims a precision the file never
 * had. A non-integer always keeps up to two decimals regardless of magnitude: a mean
 * year of manufacture (2,025.97) needs exactly the digits that make it a mean rather
 * than a year, and rounding them away because the figure is "large" would silently
 * change 2,025.97 into 2,026 - a different number, not a shorter rendering of the same
 * one. A large genuinely-fractional sum keeps its own decimals for the same reason.
 */
export function formatMeasure(value: number, language: string): string {
  if (Number.isInteger(value)) return value.toLocaleString(language);
  return value.toLocaleString(language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * A ratio against an expected value, written the way people say it out loud: 2.3x, or
 * 0.4x when the cell holds less than its share. One decimal, for the same reason
 * percentages take one.
 *
 * The one exception is ratios under a tenth, which get a second decimal. At a single
 * decimal a cell holding a twentieth of what it should reads "0.0x", which is how a
 * genuinely empty cell reads too - and the difference between almost-none and none is
 * exactly what this measure exists to show. The threshold is kept at a tenth rather than
 * applied to everything below one, so a column of these still lines up at one decimal
 * everywhere the extra digit buys nothing.
 */
export function formatMultiple(value: number, language: string): string {
  return `${value.toLocaleString(language, {
    minimumFractionDigits: 1,
    maximumFractionDigits: value !== 0 && Math.abs(value) < 0.1 ? 2 : 1,
  })}×`;
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
