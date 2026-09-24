/**
 * One place that decides how a number is written.
 *
 * The same fault the date module was built for, one type over. `toLocaleString()` with
 * no argument asks the *browser* what language it is in and never asks the app: the
 * grouping separator, and on some locales the digits themselves, come from a setting
 * the app does not control and the reader may not have chosen. An Arabic page read on a
 * German browser prints "125.375", which in Arabic is a number a thousand times smaller
 * with a decimal point.
 *
 * It is invisible on most machines, which is what makes it worth a module rather than a
 * fix: the app's own language is the answer everywhere, and asking for it at each of the
 * thirty call sites is thirty chances to forget.
 *
 * Arabic resolves to Latin digits here, not Arabic-Indic ones - `Intl.NumberFormat("ar")`
 * reports numberingSystem "latn", and only the regional forms like "ar-EG" use "arab".
 * That is checked rather than assumed; see backend/tests/test_number_formatting.py.
 */

const cache = new Map<string, Intl.NumberFormat>();

function formatter(language: string): Intl.NumberFormat {
  const key = language || "en";
  let found = cache.get(key);
  if (!found) {
    found = new Intl.NumberFormat(key);
    cache.set(key, found);
  }
  return found;
}

/** A count or a measurement, grouped the way the app's language groups numbers. */
export function formatNumber(value: number | null | undefined, language: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return formatter(language).format(value);
}

/**
 * A byte count as a number and a unit: "2.1 KB", "826 MB".
 *
 * Wrapped in a directional isolate, because the unit is Latin and most of this app is
 * not: dropped into an Arabic line, the bidirectional algorithm reorders the pair and
 * "2.1 KB" is rendered "KB 2.1". The isolate is two invisible characters saying "read
 * what is between us left to right, and do not let it disturb what is around it".
 */
export function formatBytes(
  bytes: number | null | undefined,
  language = "en"
): string {
  if (bytes === null || bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = bytes || 0;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  const digits = i === 0 ? 0 : 1;
  const size = new Intl.NumberFormat(language || "en", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
  return isolate(`${size} ${units[i]}`);
}

/** U+2066 LEFT-TO-RIGHT ISOLATE ... U+2069 POP DIRECTIONAL ISOLATE.
 *
 *  Written as escapes on purpose: both characters are invisible, and a maintainer who
 *  cannot see them cannot avoid deleting them. */
function isolate(text: string): string {
  return `\u2066${text}\u2069`;
}
