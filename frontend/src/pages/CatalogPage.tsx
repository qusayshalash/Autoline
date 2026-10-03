import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { fetchVehiclePhoto, lookupVehicle, type VehicleMatch } from "../api/catalog";
import { apiErrorMessage } from "../api/client";
import { columnLabel } from "../data/columnDictionary";
import { formatDate, formatYearMonth, isBeforeToday } from "../data/datetime";
import { makeName, translateValue } from "../data/valueDictionary";
import "../catalog.css";

/*
 * The vehicle catalog: one car, by its plate or its chassis number.
 *
 * Everything else in the app is about many rows. This is the question asked at a counter
 * with a document in hand - "what is this car?" - so the page is a single box, and the
 * answer is laid out to be read, not scanned: grouped the way somebody thinks about a car
 * rather than in the order the registry's columns happen to come in.
 *
 * The query lives in the address (/catalog?q=4910766), so a result can be bookmarked,
 * sent to someone, and survives the back button.
 */

/** How the registry's columns group into things a person recognises. A column not named
 *  here still appears, under "other" - the catalog never hides a field it was given. */
const SECTIONS: { key: string; columns: string[] }[] = [
  {
    key: "vehicle",
    columns: [
      "tozeret_nm", "kinuy_mishari", "degem_nm", "ramat_gimur", "shnat_yitzur",
      "tzeva_rechev", "sug_degem",
    ],
  },
  { key: "licence", columns: ["tokef_dt", "mivchan_acharon_dt", "moed_aliya_lakvish"] },
  {
    key: "engine",
    columns: ["degem_manoa", "sug_delek_nm", "kvutzat_zihum", "ramat_eivzur_betihuty"],
  },
  { key: "tyres", columns: ["zmig_kidmi", "zmig_ahori"] },
  {
    key: "registration",
    columns: ["mispar_rechev", "misgeret", "baalut", "horaat_rishum", "tozeret_cd", "degem_cd", "tzeva_cd"],
  },
];

const PLATE = "mispar_rechev";
const MAKE = "tozeret_nm";
const MODEL = "kinuy_mishari";
const MODEL_CODE = "degem_nm";
const YEAR = "shnat_yitzur";
const COLOUR = "tzeva_rechev";
const FUEL = "sug_delek_nm";
const LICENCE = "tokef_dt";
const ON_ROAD = "moed_aliya_lakvish";
const DATES = new Set(["tokef_dt", "mivchan_acharon_dt"]);

/** "01002085" -> "10-020-85"; "49107665" -> "491-07-665". A seven-digit plate is stored
 *  with a leading zero, and is written in two-three-two groups; an eight-digit one in
 *  three-two-three, which is how both are printed on the plate itself. */
export function formatPlate(stored: string): string {
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

  function submit(e: FormEvent) {
    e.preventDefault();
    const next = draft.trim();
    if (!next) return;
    setParams({ q: next });
    // a repeated search for the same number should still look like it did something
    if (next === q) result.refetch();
  }

  const searched = q.length > 0;

  return (
    <div className="catalog">
      <header className="catalog-bar">
        <Link to="/" className="catalog-brand">
          AutoLine
        </Link>
        <span className="catalog-bar-title">{t("catalog.title")}</span>
        <Link to="/" className="catalog-back">
          {t("catalog.back")}
        </Link>
      </header>

      <main className={`catalog-main${searched ? " has-query" : ""}`}>
        <form className="catalog-search" onSubmit={submit} role="search">
          {!searched && <h1 className="catalog-heading">{t("catalog.heading")}</h1>}
          <label htmlFor="catalog-q" className="sr-only">
            {t("catalog.label")}
          </label>
          <div className="catalog-box">
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
            <button type="submit" disabled={!draft.trim()}>
              {t("catalog.search")}
            </button>
          </div>
          {!searched && <p className="catalog-hint">{t("catalog.hint")}</p>}
        </form>

        <section aria-live="polite" className="catalog-results">
          {searched && result.isFetching && !result.data && (
            <p className="catalog-state">{t("catalog.searching")}</p>
          )}
          {result.isError && (
            <p className="catalog-state error">
              {apiErrorMessage(result.error, t("common.error_generic"))}
            </p>
          )}
          {result.data && result.data.kind === null && (
            <p className="catalog-state">{t("catalog.unreadable")}</p>
          )}
          {result.data && result.data.kind && result.data.matches.length === 0 && (
            <div className="catalog-empty">
              <strong>{t("catalog.not_found_title")}</strong>
              <p>
                {result.data.kind === "plate"
                  ? t("catalog.not_found_plate", { plate: formatPlate(result.data.normalized) })
                  : t("catalog.not_found_chassis", { chassis: result.data.normalized })}
              </p>
            </div>
          )}
          {result.data && result.data.matches.length > 1 && (
            <p className="catalog-state warn">
              {t("catalog.several", { count: result.data.matches.length })}
            </p>
          )}
          {result.data?.matches.map((m, i) => (
            <VehicleCard key={`${m.dataset_id}-${i}`} match={m} />
          ))}
        </section>
      </main>
    </div>
  );
}

function VehicleCard({ match }: { match: VehicleMatch }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const get = (col: string) => {
    const i = match.columns.indexOf(col);
    return i === -1 ? "" : match.values[i] ?? "";
  };
  const show = (col: string): string => {
    const v = get(col);
    if (!v) return "";
    if (col === PLATE) return formatPlate(v);
    if (DATES.has(col)) return formatDate(v, lang);
    if (col === ON_ROAD) return formatYearMonth(v, lang);
    if (col === "sug_degem") return t(`catalog.kind.${v}`, { defaultValue: v });
    return translateValue(v, lang);
  };

  const make = get(MAKE);
  const model = get(MODEL) || get(MODEL_CODE);
  const title = [make ? makeName(make, lang) : "", model].filter(Boolean).join(" ");
  const facts = [get(YEAR), show(COLOUR), show(FUEL)].filter(Boolean);

  const licence = get(LICENCE);
  const expired = isBeforeToday(licence);

  const placed = new Set(SECTIONS.flatMap((s) => s.columns));
  const other = match.columns.filter((c) => !placed.has(c));
  const sections = [
    ...SECTIONS.map((s) => ({ key: s.key, columns: s.columns.filter((c) => match.columns.includes(c)) })),
    { key: "other", columns: other },
  ].filter((s) => s.columns.length > 0);

  return (
    <article className="vehicle">
      <div className="vehicle-head">
        <div className="vehicle-identity">
          {get(PLATE) && (
            <span className="plate" dir="ltr" aria-label={t("catalog.plate") ?? ""}>
              {formatPlate(get(PLATE))}
            </span>
          )}
          <h2 dir="auto">{title || t("catalog.unnamed")}</h2>
          {facts.length > 0 && <p className="vehicle-facts">{facts.join(" · ")}</p>}
          {licence && (
            <span className={`licence-pill ${expired ? "expired" : "valid"}`}>
              {expired
                ? t("catalog.licence_expired", { date: formatDate(licence, lang) })
                : t("catalog.licence_valid", { date: formatDate(licence, lang) })}
            </span>
          )}
        </div>
        <VehiclePicture make={make ? makeName(make, "en") : ""} model={model} alt={title} />
      </div>

      <div className="vehicle-sections">
        {sections.map((s) => (
          <Section key={s.key} title={t(`catalog.section.${s.key}`)}>
            {s.columns.map((c) => {
              const value = show(c);
              const raw = get(c);
              return (
                <div key={c} className="vehicle-field">
                  <dt>{columnLabel(c, lang)}</dt>
                  <dd dir="auto" className={value ? "" : "empty"}>
                    {value || "—"}
                    {/* the stored Hebrew beside the translation, where they differ: it is
                        what an official document will say */}
                    {value && raw && value !== raw && !DATES.has(c) && c !== PLATE && c !== ON_ROAD && (
                      <span className="vehicle-original" dir="rtl" lang="he">
                        {raw}
                      </span>
                    )}
                  </dd>
                </div>
              );
            })}
          </Section>
        ))}
      </div>

      <p className="vehicle-source" dir="auto">
        {t("catalog.from_file", { name: match.dataset_name })}
      </p>
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="vehicle-section">
      <h3>{title}</h3>
      <dl>{children}</dl>
    </section>
  );
}

function VehiclePicture({ make, model, alt }: { make: string; model: string; alt: string }) {
  const { t } = useTranslation();
  const [broken, setBroken] = useState(false);
  const photo = useQuery({
    queryKey: ["catalog-photo", make, model],
    queryFn: () => fetchVehiclePhoto(make, model),
    enabled: !!make,
    staleTime: Infinity,
    retry: false,
  });

  const url = !broken ? photo.data?.url : null;

  return (
    <figure className="vehicle-photo">
      {url ? (
        // not lazy: the photo is at the top of the answer, already in view, and lazy
        // loading an image in view only delays it - here it held the request back entirely
        <img
          src={url}
          alt={alt}
          referrerPolicy="no-referrer"
          onError={() => setBroken(true)}
        />
      ) : (
        <div className={`vehicle-photo-empty${photo.isFetching ? " loading" : ""}`} aria-hidden="true">
          <CarGlyph />
        </div>
      )}
      <figcaption>
        {url ? (
          <>
            {t("catalog.photo_caption")}{" "}
            <a href={photo.data?.page ?? "#"} target="_blank" rel="noreferrer noopener">
              {t("catalog.photo_source")}
            </a>
          </>
        ) : photo.isFetching ? (
          t("catalog.photo_loading")
        ) : (
          t("catalog.photo_none")
        )}
      </figcaption>
    </figure>
  );
}

function CarGlyph() {
  return (
    <svg viewBox="0 0 64 32" width="96" height="48" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M6 22h52M10 22l4-9c1-2 3-3 5-3h22c2 0 4 1 5 3l5 9" strokeLinejoin="round" />
      <path d="M4 22v4h6M54 26h6v-4" strokeLinecap="round" />
      <circle cx="18" cy="26" r="4" />
      <circle cx="46" cy="26" r="4" />
    </svg>
  );
}
