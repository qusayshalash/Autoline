import { useTranslation } from "react-i18next";

import { type RecordCard } from "../api/client";
import { daysUntil, formatCalendarDate } from "../data/datetime";
import { formatPlate } from "../data/plate";
import { HEADLINE } from "../data/recordSections";
import { translateValue } from "../data/valueDictionary";

/**
 * Sends a vehicle on WhatsApp: a short summary in the reader's language - what the car is,
 * its plate, chassis and engine, whether its licence is in force - and the link to its
 * card. It opens WhatsApp with the message written and the person still choosing who gets
 * it; nothing is sent until they do. The link opens only for someone signed in.
 */
export default function ShareWhatsApp({ record, className = "" }: { record: RecordCard; className?: string }) {
  const { t, i18n } = useTranslation();
  const text = withLink(summary(record, t, i18n.language), window.location.href);

  return (
    <a
      className={`share-wa ${className}`}
      href={`https://wa.me/?text=${encodeURIComponent(text)}`}
      target="_blank"
      rel="noopener noreferrer"
    >
      <svg viewBox="0 0 20 20" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M10 2.8a7.2 7.2 0 0 0-6.2 10.9L2.8 17.2l3.6-.9A7.2 7.2 0 1 0 10 2.8z" />
        <path d="M7.4 7.2c.2-.5.5-.5.8-.5h.4c.2 0 .4.1.5.4l.6 1.4c.1.2 0 .4-.1.6l-.4.5c.4.8 1.1 1.5 2 2l.5-.4c.2-.1.4-.2.6-.1l1.4.6c.3.1.4.3.4.5v.4c0 .3-.1.6-.5.8-.5.3-1.4.4-2.6-.1A7 7 0 0 1 7.6 9.8c-.5-1.2-.4-2.1-.2-2.6z" />
      </svg>
      <span>{t("share.whatsapp")}</span>
    </a>
  );
}

type T = (key: string, options?: Record<string, unknown>) => string;

/**
 * The message: one labelled fact per line, link last on a line of its own.
 *
 * WhatsApp lays the whole message out right-to-left once it starts in Arabic, and turns
 * anything that looks like a phone number into a link of its own - a plate does, even
 * inside the page address, which split the link in two. The first version also mixed
 * Arabic and Latin on one line and opened with an emoji some clients cannot show. So:
 * no emoji, each Latin value alone after its label, and every value and the link wrapped
 * in LEFT-TO-RIGHT EMBEDDING ... POP DIRECTIONAL FORMATTING, which WhatsApp honours (the
 * newer isolates it ignored).
 */
const LRE = "\u202A";
const PDF = "\u202C";
const ltr = (value: string) => `${LRE}${value}${PDF}`;

function summary(record: RecordCard, t: T, lang: string): string {
  const get = (column: string) => {
    const i = record.columns.indexOf(column);
    const v = i === -1 ? null : record.values[i];
    return v === null || v === undefined ? "" : String(v).trim();
  };

  const lines: string[] = [];
  const make = get(HEADLINE.make) ? translateValue(get(HEADLINE.make), lang) : "";
  const model = get(HEADLINE.trade) || get(HEADLINE.model);
  if (make) lines.push(t("share.make", { value: make }));
  if (model) lines.push(t("share.model", { value: ltr(model) }));
  if (get(HEADLINE.year)) lines.push(t("share.year", { value: ltr(get(HEADLINE.year)) }));
  if (get("mispar_rechev")) lines.push(t("share.plate", { value: ltr(formatPlate(get("mispar_rechev"))) }));
  if (get("misgeret")) lines.push(t("share.chassis", { value: ltr(get("misgeret")) }));
  if (get("degem_manoa")) lines.push(t("share.engine", { value: ltr(get("degem_manoa")) }));

  const until = get(HEADLINE.licenceUntil);
  const days = until ? daysUntil(until) : null;
  if (days !== null) {
    lines.push(t(`share.licence_${days < 0 ? "expired" : "valid"}`, { date: formatCalendarDate(until, lang) }));
  }
  return lines.join("\n");
}

/** The link, alone on the last line after a blank one, held left to right. */
function withLink(text: string, url: string): string {
  return `${text}\n\n${ltr(url)}`;
}
