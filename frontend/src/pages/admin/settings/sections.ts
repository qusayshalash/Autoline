/** The settings page's table of contents, in one place.
 *
 * Kept out of the page component so the nav, the mobile select and the URL parameter all
 * read from the same list and cannot drift apart.
 */
export const SECTION_IDS = [
  "overview",
  "storage",
  "backups",
  "maintenance",
  "logs",
  "security",
  "system",
] as const;

export type SectionId = (typeof SECTION_IDS)[number];

export function isSectionId(value: string | null): value is SectionId {
  return value !== null && (SECTION_IDS as readonly string[]).includes(value);
}
