/**
 * One place that decides how a moment is written.
 *
 * The app was showing three shapes of the same thing. A role's "updated" read
 * "9/13/2026, 11:03:17 PM" - the American order, on an Arabic page, because
 * `toLocaleString()` with no argument asks the *browser* what language it is in and
 * never asks the app. The system panel printed "2026-09-13 23:03:16" exactly as the
 * database had it. And the activity log said "قبل ٣ دقائق", which is a different and
 * perfectly good thing to say, but it was the third.
 *
 * Underneath that, six screens each parsed and formatted inline, so each had its own
 * opinion about whether seconds belong on screen.
 *
 * The backend settled the transport side already (see backend/app/services/clocks.py):
 * every timestamp crosses the wire as an instant, with a Z or an offset. This is the
 * display side of that same rule, and the only place in the frontend that turns one
 * into text.
 */

import type { TFunction } from "i18next";

/** How long the relative form stays useful. "3 minutes ago" tells you something; "621
 *  days ago" is arithmetic the reader has to undo to learn the date. */
const RELATIVE_HORIZON_DAYS = 30;

/**
 * A timestamp from the API as a Date.
 *
 * Returns null rather than an Invalid Date so callers have one thing to check. The
 * space-separated fallback is for values that predate the clocks module and for any
 * that still reach us without a zone; those are read as UTC, which is what this
 * codebase writes.
 */
export function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null;
  const text = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
  const when = new Date(text);
  return Number.isNaN(when.getTime()) ? null : when;
}

const cache = new Map<string, Intl.DateTimeFormat>();

function formatter(language: string, options: Intl.DateTimeFormatOptions) {
  const key = `${language}|${JSON.stringify(options)}`;
  let found = cache.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(language, options);
    cache.set(key, found);
  }
  return found;
}

/** A moment, as most screens should show one: the day, and the time to the minute. */
export function formatDateTime(value: string | null | undefined, language: string): string {
  const when = parseTimestamp(value);
  if (!when) return value ? value : "—";
  return formatter(language, { dateStyle: "medium", timeStyle: "short" }).format(when);
}

/**
 * The same moment to the second.
 *
 * Only where the record is evidence and the exact instant is the point - the activity
 * log, where two entries a few seconds apart are the difference between one action and
 * two. Everywhere else the seconds are noise, which is why they are not the default.
 */
export function formatInstant(value: string | null | undefined, language: string): string {
  const when = parseTimestamp(value);
  if (!when) return value ? value : "—";
  return formatter(language, { dateStyle: "medium", timeStyle: "medium" }).format(when);
}

/** A day, where the time of day is not part of what is being said. */
export function formatDate(value: string | null | undefined, language: string): string {
  const when = parseTimestamp(value);
  if (!when) return value ? value : "—";
  return formatter(language, { dateStyle: "medium" }).format(when);
}

/**
 * How long ago, in words - but only while that is the more useful sentence.
 *
 * Past the horizon it gives the date instead. "قبل 621 يومًا" is technically an answer
 * and practically a subtraction problem; the reader wanted to know when.
 */
export function formatRelative(
  value: string | null | undefined,
  t: TFunction,
  language: string
): string {
  const when = parseTimestamp(value);
  if (!when) return "—";
  const seconds = Math.round((Date.now() - when.getTime()) / 1000);
  if (seconds < 0) return formatDateTime(value, language); // a clock ahead of ours
  if (seconds < 60) return t("admin.time.just_now");
  if (seconds < 3600) return t("admin.time.minutes", { count: Math.floor(seconds / 60) });
  if (seconds < 86_400) return t("admin.time.hours", { count: Math.floor(seconds / 3600) });
  const days = Math.floor(seconds / 86_400);
  if (days > RELATIVE_HORIZON_DAYS) return formatDate(value, language);
  return t("admin.time.days", { count: days });
}
