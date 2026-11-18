import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { lookupVehicle, type VehicleMatch } from "../api/catalog";
import { apiErrorMessage, type RecordCard } from "../api/client";
import RecordCardView from "../components/RecordCardView";
import { useTheme } from "../theme/ThemeContext";
import "../catalog.css";

/*
 * The vehicle catalog: one car, by its plate or its chassis number.
 *
 * Everything else in the app is about many rows. This is the question asked at a counter
 * with a document in hand - "what is this car?" - so before a search the page is the box
 * and little else, and after one the box shrinks to a bar above the answer.
 *
 * The query lives in the address (/catalog?q=4910766), so a result can be bookmarked,
 * sent to someone, and survives the back button.
 *
 * The answer is the same card the grid opens from a row number (RecordCardView) - one look
 * for a car, however it was reached. No photo: Qusay chose to drop it (2026-11-18).
 */

const PLATE = "mispar_rechev";
/** What the hint offers to try: a plate as it is printed. */
const EXAMPLE_PLATE = "49-107-66";

/** The last few numbers looked up, kept in this browser only - a convenience for whoever
 *  sits at this counter, never sent anywhere. Any failure just means no list. */
const RECENT_KEY = "catalog.recent";
const RECENT_MAX = 6;

function readRecent(): string[] {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(list) ? list.filter((x) => typeof x === "string").slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

function writeRecent(list: string[]) {
  try {
    if (list.length) localStorage.setItem(RECENT_KEY, JSON.stringify(list));
    else localStorage.removeItem(RECENT_KEY);
  } catch {
    // private window or storage blocked: the list is a nicety
  }
}

/** "01002085" -> "10-020-85"; "49107665" -> "491-07-665". A seven-digit plate is stored
 *  with a leading zero, and is written in two-three-two groups; an eight-digit one in
 *  three-two-three, which is how both are printed on the plate itself. */
function formatPlate(stored: string): string {
  const digits = (stored || "").replace(/\D/g, "");
  if (digits.length === 8 && digits.startsWith("0")) {
    const d = digits.slice(1);
    return `${d.slice(0, 2)}-${d.slice(2, 5)}-${d.slice(5)}`;
  }
  if (digits.length === 8) return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
  if (digits.length === 7) return `${digits.slice(0, 2)}-${digits.slice(2, 5)}-${digits.slice(5)}`;
  return stored;
}

export default function CatalogPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const [draft, setDraft] = useState(q);
  const [recent, setRecent] = useState<string[]>(readRecent);
  const inputRef = useRef<HTMLInputElement>(null);

  // the box follows the address, so back and forward put the right number in it
  useEffect(() => setDraft(q), [q]);
  useEffect(() => inputRef.current?.focus(), []);

  const result = useQuery({
    queryKey: ["catalog", q],
    queryFn: () => lookupVehicle(q),
    enabled: q.length > 0,
    staleTime: 60 * 1000,
  });

  // a number goes on the recent list once it has found a vehicle, not merely been typed
  useEffect(() => {
    if (!result.data?.matches.length) return;
    setRecent((prev) => {
      const next = [q, ...prev.filter((x) => x !== q)].slice(0, RECENT_MAX);
      writeRecent(next);
      return next;
    });
  }, [result.data, q]);

  function search(value: string) {
    const next = value.trim();
    if (!next) return;
    setDraft(next);
    setParams({ q: next });
    // a repeated search for the same number should still look like it did something
    if (next === q) result.refetch();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    search(draft);
  }

  function clearRecent() {
    writeRecent([]);
    setRecent([]);
  }

  const searched = q.length > 0;
  const data = result.data;
  const loading = searched && result.isFetching && !data;

  return (
    <div className={`catalog${searched ? " has-query" : ""}`}>
      <header className="catalog-bar">
        <div className="catalog-bar-inner">
          <Link to="/" className="catalog-brand">
            <span className="catalog-brand-mark" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
            </span>
            <span className="catalog-brand-copy">
              <strong lang="en">AutoLine</strong>
              <small>{t("catalog.title")}</small>
            </span>
          </Link>
          <div className="catalog-bar-actions">
            <ThemeSwitch />
            <Link to="/" className="catalog-back">
              <IconArrow />
              <span>{t("catalog.back")}</span>
            </Link>
          </div>
        </div>
      </header>

      <main className="catalog-main">
        <section className="catalog-hero">
          {!searched && (
            <div className="catalog-intro">
              <span className="catalog-eyebrow">
                <IconCar />
                {t("catalog.eyebrow")}
              </span>
              <h1 className="catalog-heading">{t("catalog.heading")}</h1>
              <p className="catalog-sub">{t("catalog.sub")}</p>
            </div>
          )}

          <form className="catalog-search" onSubmit={submit} role="search">
            <label htmlFor="catalog-q" className="sr-only">
              {t("catalog.label")}
            </label>
            <div className="catalog-box">
              <span className="catalog-box-icon" aria-hidden="true">
                <IconSearch />
              </span>
              <input
                id="catalog-q"
                ref={inputRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={t("catalog.placeholder") ?? ""}
                autoComplete="off"
                spellCheck={false}
                inputMode="text"
                dir="ltr"
                maxLength={64}
              />
              {draft && (
                <button
                  type="button"
                  className="catalog-clear"
                  onClick={() => {
                    setDraft("");
                    inputRef.current?.focus();
                  }}
                  aria-label={t("catalog.clear") ?? ""}
                  title={t("catalog.clear") ?? ""}
                >
                  <IconClose />
                </button>
              )}
              <button type="submit" className="catalog-go" disabled={!draft.trim()}>
                <span>{t("catalog.search")}</span>
                <kbd aria-hidden="true">Enter</kbd>
              </button>
            </div>
          </form>

          {!searched && (
            <div className="catalog-helpers">
              <p className="catalog-hint">
                <span>{t("catalog.try")}</span>
                <button
                  type="button"
                  className="mini-plate"
                  dir="ltr"
                  onClick={() => search(EXAMPLE_PLATE)}
                >
                  {EXAMPLE_PLATE}
                </button>
                <span className="catalog-hint-sep" aria-hidden="true">·</span>
                <span>{t("catalog.chassis_hint")}</span>
              </p>

              {recent.length > 0 && (
                <div className="catalog-recent">
                  <span className="catalog-recent-label">
                    <IconClock />
                    {t("catalog.recent")}
                  </span>
                  <div className="catalog-recent-list">
                    {recent.map((r) => (
                      <button key={r} type="button" dir="ltr" onClick={() => search(r)}>
                        {/^\d[\d\s-]*$/.test(r) ? formatPlate(r.replace(/\D/g, "")) : r}
                      </button>
                    ))}
                  </div>
                  <button type="button" className="catalog-recent-clear" onClick={clearRecent}>
                    {t("catalog.recent_clear")}
                  </button>
                </div>
              )}
            </div>
          )}
        </section>

        {!searched && (
          <ul className="catalog-tips">
            <Tip icon={<IconHash />} title={t("catalog.tip_any_title")} text={t("catalog.tip_any_text")} />
            <Tip icon={<IconFiles />} title={t("catalog.tip_files_title")} text={t("catalog.tip_files_text")} />
            <Tip icon={<IconShield />} title={t("catalog.tip_card_title")} text={t("catalog.tip_card_text")} />
          </ul>
        )}

        {searched && (
          <section aria-live="polite" aria-busy={loading} className="catalog-results">
            {data?.kind && (
              <p className="catalog-meta">
                <span className="catalog-meta-kind">
                  {data.kind === "plate" ? t("catalog.kind_plate") : t("catalog.kind_chassis")}
                </span>
                {data.kind === "plate" ? (
                  <span className="mini-plate static" dir="ltr">
                    {formatPlate(data.normalized)}
                  </span>
                ) : (
                  <bdi className="catalog-meta-vin" dir="ltr">
                    {data.normalized}
                  </bdi>
                )}
                {data.matches.length > 0 && (
                  <span className="catalog-meta-count">
                    {t("catalog.found", { count: data.matches.length })}
                  </span>
                )}
              </p>
            )}

            {loading && <CardSkeleton label={t("catalog.searching")} />}

            {result.isError && (
              <Notice tone="danger" icon={<IconAlert />}>
                {apiErrorMessage(result.error, t("common.error_generic"))}
              </Notice>
            )}

            {data && data.kind === null && (
              <Notice tone="warn" icon={<IconAlert />} title={t("catalog.unreadable_title")}>
                {t("catalog.unreadable")}
              </Notice>
            )}

            {data && data.kind && data.matches.length === 0 && (
              <div className="catalog-empty">
                <span className="catalog-empty-icon" aria-hidden="true">
                  <IconSearchOff />
                </span>
                <strong>{t("catalog.not_found_title")}</strong>
                <p>
                  {data.kind === "plate"
                    ? t("catalog.not_found_plate", { plate: formatPlate(data.normalized) })
                    : t("catalog.not_found_chassis", { chassis: data.normalized })}
                </p>
                <ul className="catalog-empty-tips">
                  <li>{t("catalog.not_found_tip_digits")}</li>
                  <li>{t("catalog.not_found_tip_files")}</li>
                </ul>
              </div>
            )}

            {data && data.matches.length > 1 && (
              <Notice tone="info" icon={<IconInfo />}>
                {t("catalog.several", { count: data.matches.length })}
              </Notice>
            )}

            {data?.matches.map((m, i) => (
              <VehicleCard key={`${m.dataset_id}-${i}`} match={m} />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}

function VehicleCard({ match }: { match: VehicleMatch }) {
  const { t } = useTranslation();
  const get = (col: string) => {
    const i = match.columns.indexOf(col);
    return i === -1 ? "" : match.values[i] ?? "";
  };

  // The lookup answers with the row as the file has it; the card reads a record. The plate
  // is the key when the file has one. No arrival mark, and no corrections history - the
  // catalog is read access, and who corrected what is not for every reader.
  const plate = get(PLATE);
  const record: RecordCard = {
    columns: match.columns,
    values: match.values,
    key_columns: plate ? [PLATE] : [],
    key: plate ? [plate] : [],
    arrival: null,
    corrections: null,
  };

  // With several matches on the page, only the card whose button was pressed goes to
  // paper: it is marked, the rest are hidden by the print stylesheet, and the mark comes
  // off once the print dialog closes.
  const ref = useRef<HTMLElement>(null);
  function print() {
    const card = ref.current;
    if (!card) return;
    document.body.classList.add("printing-one");
    card.classList.add("print-target");
    const done = () => {
      document.body.classList.remove("printing-one");
      card.classList.remove("print-target");
      window.removeEventListener("afterprint", done);
    };
    window.addEventListener("afterprint", done);
    window.print();
  }

  return (
    <article className="catalog-card" ref={ref}>
      <RecordCardView record={record} source={match.dataset_name} />
      <div className="catalog-card-foot">
        <p className="catalog-card-source" dir="auto">
          <IconFile />
          <span>{t("catalog.from_file", { name: match.dataset_name })}</span>
        </p>
        <button type="button" className="catalog-print" onClick={print}>
          <IconPrinter />
          <span>{t("record.print")}</span>
        </button>
      </div>
    </article>
  );
}

/** Light or dark, as a sliding switch: the sun and the moon sit at either end of the
 *  track and the thumb carries the one in force. A choice made here is the same setting
 *  the rest of the app uses. */
function ThemeSwitch() {
  const { t } = useTranslation();
  const { resolved, setMode } = useTheme();
  const isDark = resolved === "dark";
  const label = t(isDark ? "theme.light" : "theme.dark") ?? "";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      aria-label={t("theme.label") ?? "Theme"}
      title={label}
      className={`catalog-theme${isDark ? " is-dark" : ""}`}
      onClick={() => setMode(isDark ? "light" : "dark")}
      dir="ltr"
    >
      <span className="catalog-theme-end sun" aria-hidden="true">
        <IconSun />
      </span>
      <span className="catalog-theme-end moon" aria-hidden="true">
        <IconMoon />
      </span>
      <span className="catalog-theme-thumb" aria-hidden="true">
        {isDark ? <IconMoon /> : <IconSun />}
      </span>
    </button>
  );
}

function Tip({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <li className="catalog-tip">
      <span className="catalog-tip-icon" aria-hidden="true">
        {icon}
      </span>
      <strong>{title}</strong>
      <span>{text}</span>
    </li>
  );
}

function Notice({
  tone,
  icon,
  title,
  children,
}: {
  tone: "info" | "warn" | "danger";
  icon: ReactNode;
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={`catalog-notice ${tone}`} role={tone === "danger" ? "alert" : undefined}>
      <span className="catalog-notice-icon" aria-hidden="true">
        {icon}
      </span>
      <div>
        {title && <strong>{title}</strong>}
        <p>{children}</p>
      </div>
    </div>
  );
}

/** The card's shape while the lookup runs, so the answer lands where the eye already is. */
function CardSkeleton({ label }: { label: string }) {
  return (
    <div className="catalog-skeleton" role="status">
      <span className="sr-only">{label}</span>
      <div className="sk sk-hero">
        <div className="sk-lines">
          <span className="sk-bar w30" />
          <span className="sk-bar w60 tall" />
          <span className="sk-bar w40" />
        </div>
        <span className="sk-plate" />
      </div>
      <div className="sk-tiles">
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className="sk sk-tile" />
        ))}
      </div>
      <div className="sk-sections">
        <span className="sk sk-section" />
        <span className="sk sk-section" />
      </div>
    </div>
  );
}

/* ---- icons: 20px grid, drawn with the current colour ---------------------------- */

const svg = {
  width: 18,
  height: 18,
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function IconSearch() {
  return (
    <svg {...svg} width={20} height={20}>
      <circle cx="8.8" cy="8.8" r="5.6" />
      <path d="M13 13l4 4" />
    </svg>
  );
}
function IconSearchOff() {
  return (
    <svg {...svg} width={26} height={26}>
      <circle cx="8.8" cy="8.8" r="5.6" />
      <path d="M13 13l4 4M6.8 6.8l4 4M10.8 6.8l-4 4" />
    </svg>
  );
}
function IconClose() {
  return (
    <svg {...svg} width={16} height={16}>
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  );
}
function IconArrow() {
  // drawn pointing left; the stylesheet turns it for a right-to-left page
  return (
    <svg {...svg} width={16} height={16} className="catalog-back-arrow">
      <path d="M12 5l-5 5 5 5" />
    </svg>
  );
}
function IconCar() {
  return (
    <svg {...svg} width={16} height={16}>
      <path d="M3 12.5h14M4.5 12.5l1.6-4.2c.3-.8 1-1.3 1.9-1.3h4c.9 0 1.6.5 1.9 1.3l1.6 4.2" />
      <path d="M3 12.5v2.5h2M15 15h2v-2.5" />
      <circle cx="6.5" cy="15" r="1.3" />
      <circle cx="13.5" cy="15" r="1.3" />
    </svg>
  );
}
function IconSun() {
  return (
    <svg {...svg} width={14} height={14} strokeWidth={1.9}>
      <circle cx="10" cy="10" r="3.4" />
      <path d="M10 2.5v1.8M10 15.7v1.8M17.5 10h-1.8M4.3 10H2.5M15.3 4.7l-1.3 1.3M6 14l-1.3 1.3M15.3 15.3L14 14M6 6L4.7 4.7" />
    </svg>
  );
}
function IconMoon() {
  return (
    <svg {...svg} width={14} height={14} strokeWidth={1.9}>
      <path d="M16.5 11.8A6.8 6.8 0 0 1 8.2 3.5a6.9 6.9 0 1 0 8.3 8.3z" />
    </svg>
  );
}
function IconClock() {
  return (
    <svg {...svg} width={15} height={15}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6v4l2.5 1.5" />
    </svg>
  );
}
function IconHash() {
  return (
    <svg {...svg}>
      <path d="M7.5 3L6 17M14 3l-1.5 14M3.5 7.5h13M3 12.5h13" />
    </svg>
  );
}
function IconFiles() {
  return (
    <svg {...svg}>
      <path d="M6 3.5h5.5L15 7v9.5H6z" />
      <path d="M11.5 3.5V7H15M3.5 6v12h9" />
    </svg>
  );
}
function IconShield() {
  return (
    <svg {...svg}>
      <path d="M10 2.8l6 2.4v4.5c0 3.6-2.5 6.4-6 7.5-3.5-1.1-6-3.9-6-7.5V5.2z" />
      <path d="M7.3 10.2l1.9 1.9 3.6-3.8" />
    </svg>
  );
}
function IconFile() {
  return (
    <svg {...svg} width={14} height={14}>
      <path d="M5 2.5h6.5L15 6v11.5H5z" />
      <path d="M11.5 2.5V6H15" />
    </svg>
  );
}
function IconPrinter() {
  return (
    <svg {...svg} width={16} height={16}>
      <path d="M5.5 7.5V3h9v4.5" />
      <rect x="2.5" y="7.5" width="15" height="7" rx="1.6" />
      <path d="M5.5 12h9v5h-9z" />
      <path d="M14.5 10h.01" />
    </svg>
  );
}
function IconAlert() {
  return (
    <svg {...svg}>
      <path d="M10 3l7.5 13h-15z" />
      <path d="M10 8.2v3.6M10 14.2v.1" />
    </svg>
  );
}
function IconInfo() {
  return (
    <svg {...svg}>
      <circle cx="10" cy="10" r="7.2" />
      <path d="M10 9v4.5M10 6.4v.1" />
    </svg>
  );
}
