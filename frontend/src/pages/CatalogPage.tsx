import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { lookupVehicle, type VehicleMatch } from "../api/catalog";
import { apiErrorMessage, type RecordCard } from "../api/client";
import RecordCardView from "../components/RecordCardView";
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
 *
 * The answer is the same card the grid opens from a row number (RecordCardView) - one look
 * for a car, however it was reached. No photo: Qusay chose to drop it (2026-11-18).
 */

const PLATE = "mispar_rechev";

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

  return (
    <article className="catalog-card">
      <RecordCardView record={record} />
      <p className="catalog-card-source" dir="auto">
        {t("catalog.from_file", { name: match.dataset_name })}
      </p>
    </article>
  );
}
