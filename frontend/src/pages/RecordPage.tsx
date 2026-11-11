import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";

import {
  apiErrorMessage,
  fetchRecord,
  getDataset,
  type Correction,
  type RecordCard,
} from "../api/client";
import ArrivalMark from "../components/ArrivalMark";
import ErrorBanner from "../components/ErrorBanner";
import LoadingState from "../components/LoadingState";
import SemanticIcon from "../components/SemanticIcons";
import { columnLabel, columnMeta, usesRawHeaders } from "../data/columnDictionary";
import {
  daysUntil,
  formatCalendarDate,
  formatDate,
  formatDateTime,
  relativeDays,
} from "../data/datetime";
import {
  CODE_COLUMNS,
  DATE_COLUMNS,
  HEADLINE,
  RECORD_SECTIONS,
  type SectionId,
} from "../data/recordSections";
import { hasHebrew, translateValue } from "../data/valueDictionary";

/** Within this many days of expiry a licence is flagged as due rather than valid. */
const LICENCE_DUE_DAYS = 30;

/**
 * One record, whole: the vehicle card.
 *
 * Read top to bottom the way the questions come. What is it - the make and model as a
 * heading, the plate beside it. Is it on the road legally - the licence and the last test
 * as two statuses, coloured by what they mean. Then the details, grouped, with the
 * internal codes last and quietest. Then, for whoever may see it, what was changed by
 * hand and by whom.
 */
export default function RecordPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { datasetId = "" } = useParams();
  const [params] = useSearchParams();
  const key = params.getAll("key");
  const [copied, setCopied] = useState(false);

  const { data: dataset } = useQuery({
    queryKey: ["dataset", datasetId],
    queryFn: () => getDataset(datasetId),
  });
  const { data: record, error, isLoading } = useQuery({
    queryKey: ["record", datasetId, key],
    queryFn: () => fetchRecord(datasetId, key),
    enabled: key.length > 0,
    retry: false,
  });

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      // nothing to copy to; the address bar still has it
    }
  }

  return (
    <div className="record-page">
      <div className="record-topbar">
        <Link to={`/datasets/${datasetId}/explore`} className="sheet-back">
          {t("record.back")}
        </Link>
        <span className="record-file" dir="auto" title={dataset?.original_filename}>
          {dataset?.original_filename ?? "…"}
        </span>
        {record && (
          <button type="button" className="btn secondary record-copy" onClick={copyLink}>
            {copied ? t("record.link_copied") : t("record.copy_link")}
          </button>
        )}
      </div>

      {key.length === 0 ? (
        <ErrorBanner message={t("errors.row_not_found")} />
      ) : isLoading ? (
        <LoadingState />
      ) : error || !record ? (
        <ErrorBanner message={apiErrorMessage(error, t("common.error_generic"))} />
      ) : (
        <Card record={record} lang={lang} />
      )}
    </div>
  );
}

function Card({ record, lang }: { record: RecordCard; lang: string }) {
  const { t, i18n } = useTranslation();
  const raw = usesRawHeaders(lang);

  const values = new Map<string, string>();
  record.columns.forEach((c, i) => {
    const v = record.values[i];
    values.set(c, v === null || v === undefined ? "" : String(v));
  });
  const has = (c: string) => values.has(c);
  const get = (c: string) => values.get(c) ?? "";

  /** What a value reads as on the card: a date as a date, Hebrew translated. */
  const display = (column: string, value: string | null | undefined): string => {
    const text = value ?? "";
    if (!text) return "";
    if (DATE_COLUMNS.has(column)) return formatCalendarDate(text, lang);
    return raw ? text : translateValue(text, lang);
  };

  const corrections = record.corrections ?? [];
  const fixByColumn = new Map<string, Correction>(corrections.map((c) => [c.column, c]));

  // ---- the heading ----
  const make = has(HEADLINE.make) ? display(HEADLINE.make, get(HEADLINE.make)) : "";
  const title =
    (has(HEADLINE.trade) && get(HEADLINE.trade)) ||
    (has(HEADLINE.model) && get(HEADLINE.model)) ||
    record.key.join(" · ");
  const subtitle = [HEADLINE.model, HEADLINE.trim, HEADLINE.year]
    .filter((c) => has(c) && get(c) && get(c) !== title)
    .map((c) => display(c, get(c)));
  const isPlate = record.key_columns.length === 1 && record.key_columns[0] === "mispar_rechev";

  // ---- the facts strip ----
  const facts = [HEADLINE.year, HEADLINE.fuel, HEADLINE.colour, HEADLINE.ownership].filter(
    (c) => has(c) && get(c)
  );

  // ---- licence and last test ----
  const licenceDays = has(HEADLINE.licenceUntil) ? daysUntil(get(HEADLINE.licenceUntil)) : null;
  const licenceState =
    licenceDays === null
      ? null
      : licenceDays < 0
        ? "expired"
        : licenceDays <= LICENCE_DUE_DAYS
          ? "due"
          : "valid";
  const testDays = has(HEADLINE.lastTest) ? daysUntil(get(HEADLINE.lastTest)) : null;

  // ---- the sections ----
  const placed = new Set<string>();
  const sections: { id: SectionId; columns: string[] }[] = [];
  for (const s of RECORD_SECTIONS) {
    const columns = s.columns.filter(has);
    columns.forEach((c) => placed.add(c));
    if (columns.length) sections.push({ id: s.id, columns });
  }
  const rest = record.columns.filter((c) => !placed.has(c));
  if (rest.length) sections.push({ id: "other", columns: rest });
  const onlyOther = sections.length === 1 && sections[0].id === "other";

  const valueCell = (column: string): ReactNode => {
    const text = get(column);
    if (!text) return <span className="rc-empty">—</span>;
    const shown = display(column, text);
    const original = shown !== text && hasHebrew(text) ? text : undefined;
    if (CODE_COLUMNS.has(column) || record.key_columns.includes(column)) {
      return (
        <bdi className="rc-code" dir="ltr">
          {shown}
        </bdi>
      );
    }
    return (
      <bdi title={original ?? (DATE_COLUMNS.has(column) ? text : undefined)}>{shown}</bdi>
    );
  };

  return (
    <>
      <header className="rc-hero">
        <div className="rc-hero-text">
          {make && <p className="rc-make">{make}</p>}
          <h1 className="rc-title">
            <bdi>{title}</bdi>
          </h1>
          {subtitle.length > 0 && (
            <p className="rc-subtitle">
              {subtitle.map((part, i) => (
                <span key={i}>
                  {i > 0 && <span className="rc-dot" aria-hidden="true">·</span>}
                  <bdi>{part}</bdi>
                </span>
              ))}
            </p>
          )}
          {(record.arrival || corrections.length > 0) && (
            <div className="rc-chips">
              {record.arrival && (
                <span className={`rc-chip ${record.arrival.kind}`}>
                  <ArrivalMark kind={record.arrival.kind} when={record.arrival.added_at} />
                  {t(record.arrival.kind === "new" ? "arrivals.new_at" : "arrivals.updated_at", {
                    when: formatDate(record.arrival.added_at, lang),
                  })}
                </span>
              )}
              {corrections.length > 0 && (
                <span className="rc-chip corrected">
                  <PenGlyph />
                  {t("corrections.row", { count: corrections.length })}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="rc-id">
          <span className="rc-id-label">
            {record.key_columns.map((c) => columnLabel(c, lang)).join(" + ")}
          </span>
          {isPlate ? (
            <span className="rc-plate" dir="ltr">
              {formatPlate(record.key[0])}
            </span>
          ) : (
            <bdi className="rc-key">{record.key.join(" · ")}</bdi>
          )}
        </div>
      </header>

      {(facts.length > 0 || licenceState || testDays !== null) && (
        <div className="rc-glance">
          {facts.map((c) => (
            <div key={c} className="rc-fact">
              <span className="rc-fact-icon" aria-hidden="true">
                <SemanticIcon name={columnMeta(c)?.icon ?? "doc"} />
              </span>
              <span className="rc-fact-label">{columnLabel(c, lang)}</span>
              <span className="rc-fact-value">{valueCell(c)}</span>
            </div>
          ))}

          {licenceState && (
            <div className={`rc-fact rc-status ${licenceState}`}>
              <span className="rc-fact-label">{t("record.licence")}</span>
              <span className="rc-fact-value">
                <span className="rc-pill">{t(`record.licence_${licenceState}`)}</span>
              </span>
              <span className="rc-fact-note">
                {display(HEADLINE.licenceUntil, get(HEADLINE.licenceUntil))}
                {" · "}
                {relativeDays(licenceDays!, lang)}
              </span>
            </div>
          )}

          {testDays !== null && (
            <div className="rc-fact rc-status neutral">
              <span className="rc-fact-label">{t("record.last_test")}</span>
              <span className="rc-fact-value">{relativeDays(testDays, lang)}</span>
              <span className="rc-fact-note">
                {display(HEADLINE.lastTest, get(HEADLINE.lastTest))}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="rc-sections">
        {sections.map((s) => (
          <section
            key={s.id}
            className={`rc-section ${s.id}`}
            aria-labelledby={`rc-${s.id}`}
          >
            <h2 id={`rc-${s.id}`} className="rc-section-title">
              {onlyOther ? t("record.fields") : t(`record.sections.${s.id}`)}
            </h2>
            <dl className="rc-rows">
              {s.columns.map((c) => {
                const fix = fixByColumn.get(c);
                const icon = columnMeta(c)?.icon;
                return (
                  <div key={c} className={`rc-row${fix ? " is-corrected" : ""}`}>
                    <dt title={c}>
                      {icon && (
                        <span className="rc-row-icon" aria-hidden="true">
                          <SemanticIcon name={icon} />
                        </span>
                      )}
                      {columnLabel(c, lang)}
                    </dt>
                    <dd>
                      <span className="rc-value">
                        {fix && (
                          <span className="rc-pen" title={t("record.corrected")}>
                            <PenGlyph />
                          </span>
                        )}
                        {valueCell(c)}
                      </span>
                      {fix && (
                        <span className="rc-was">
                          {t("corrections.was", { value: display(c, fix.old_value) || "—" })}
                        </span>
                      )}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </section>
        ))}
      </div>

      {record.corrections !== null && (
        <section className="rc-section rc-history-card" aria-labelledby="rc-history">
          <h2 id="rc-history" className="rc-section-title">
            {t("record.history")}
          </h2>
          {corrections.length === 0 ? (
            <p className="rc-note">{t("record.no_corrections")}</p>
          ) : (
            <ol className="rc-history">
              {corrections.map((c) => (
                <li key={c.column}>
                  <span className="rc-history-dot" aria-hidden="true" />
                  <div className="rc-history-body">
                    <span className="rc-history-field">{columnLabel(c.column, lang)}</span>
                    <span className="rc-history-change">
                      <del>
                        <bdi>{display(c.column, c.old_value) || "—"}</bdi>
                      </del>
                      <span className="rc-arrow" aria-hidden="true">
                        {i18n.dir() === "rtl" ? "←" : "→"}
                      </span>
                      <ins>
                        <bdi>{display(c.column, c.new_value) || "—"}</bdi>
                      </ins>
                    </span>
                    {/* each part isolated: a Latin username beside an Arabic date
                        otherwise reorders into something that reads as neither */}
                    <span className="rc-history-who">
                      <bdi>{c.actor || "—"}</bdi>
                      <span aria-hidden="true"> · </span>
                      <bdi>{formatDateTime(c.edited_at, lang)}</bdi>
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </>
  );
}

/** An Israeli plate as it is printed: 12-345-67 for seven digits, 123-45-678 for eight.
 *  The stored number keeps its leading zeros, which are not on the plate. */
function formatPlate(value: string): string {
  const digits = value.replace(/\D/g, "").replace(/^0+(?=\d{7})/, "");
  if (digits.length === 7) return `${digits.slice(0, 2)}-${digits.slice(2, 5)}-${digits.slice(5)}`;
  if (digits.length === 8) return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
  return value;
}

function PenGlyph() {
  return (
    <svg
      width={12}
      height={12}
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M7.9 2.1l2 2L4.2 9.8 1.8 10.2l.4-2.4z" />
      <path d="M6.9 3.1l2 2" />
    </svg>
  );
}
