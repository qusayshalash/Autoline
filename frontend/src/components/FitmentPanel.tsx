import { useTranslation } from "react-i18next";

import { type Fitment, type FitmentPart, type FitmentSource, type FitmentType } from "../api/client";
import { formatNumber } from "../data/numbers";
import CopyButton from "./CopyButton";

/**
 * The filters that fit this vehicle, as the catalogues give them - each catalogue on its
 * own line, never merged into one answer behind the reader's back.
 *
 * A wrong filter damages an engine, so the section says how sure it is for every filter:
 * two catalogues from different companies naming the same part (by the car maker's own
 * original-equipment number) is "agreed"; two naming parts that share no number is a
 * contradiction, shown in red, to be settled before anything is ordered; one catalogue is
 * one catalogue. Where none fits, it says so - nothing is borrowed from a similar car.
 *
 * MANN-FILTER matched most vehicles by their chassis number, which is said beside it.
 * UFI's equivalents of the MANN part are listed apart: they are the same filter under
 * another brand (UFI's own cross-reference), not a second opinion on the vehicle.
 */

const TYPES: FitmentType[] = ["oil", "air", "fuel", "cabin"];
/** the catalogues that fit vehicles, in the order they are shown */
const SOURCES: { id: FitmentSource; name: string }[] = [
  { id: "mann", name: "MANN-FILTER" },
  { id: "jsfilter", name: "JS Filter" },
  { id: "denckermann", name: "Denckermann" },
  { id: "ufi", name: "UFI" },
];
/** MANN's way of saying the filter is sealed in for life, not a part to stock */
const LIFETIME = "LIFETIME-FILTER";

export default function FitmentPanel({ fitment }: { fitment: Fitment }) {
  const { t, i18n } = useTranslation();

  const head = (
    <div className="rc-fit-head">
      <h2 id="rc-fit-title" className="rc-section-title">
        {t("fitment.title")}
      </h2>
      {fitment.found && fitment.vehicles ? (
        <span className="rc-fit-meta">
          {t("fitment.same_config", { count: fitment.vehicles, n: formatNumber(fitment.vehicles, i18n.language) })}
        </span>
      ) : null}
    </div>
  );

  if (!fitment.found || !fitment.covered || Object.keys(fitment.filters).length === 0) {
    return (
      <section className="rc-section rc-fit" aria-labelledby="rc-fit-title">
        {head}
        <p className="rc-note">{fitment.electric ? t("fitment.electric") : t("fitment.not_covered")}</p>
      </section>
    );
  }

  const mannBy = fitment.matches.mann?.status === "matched" ? fitment.matches.mann?.detail : null;

  return (
    <section className="rc-section rc-fit" aria-labelledby="rc-fit-title">
      {head}
      <div className="rc-fit-rows">
        {TYPES.map((type) => {
          const by = fitment.filters[type] ?? {};
          const mann = by.mann ?? [];
          const lifetime = mann.length === 1 && mann[0].part === LIFETIME;
          const listed = SOURCES.filter((s) => (by[s.id]?.length ?? 0) > 0);
          const verdict = fitment.verdicts[type]?.verdict;
          const clash = new Set((fitment.verdicts[type]?.clashes ?? []).flatMap((c) => c.split("|")));

          return (
            <div key={type} className={`rc-fit-row${verdict === "disagree" ? " is-clash" : ""}`}>
              <div className="rc-fit-type">
                <strong>{t(`fitment.type_${type}`)}</strong>
                {listed.length > 0 && !lifetime && verdict && (
                  <span className={`rc-fit-verdict v-${verdict}`}>{t(`fitment.verdict_${verdict}`)}</span>
                )}
              </div>

              <div className="rc-fit-body">
                {listed.length === 0 ? (
                  <span className="rc-fit-none">{t("fitment.none")}</span>
                ) : lifetime && listed.length === 1 ? (
                  <span className="rc-fit-lifetime">{t("fitment.lifetime")}</span>
                ) : (
                  listed.map((s) => (
                    <div key={s.id} className={`rc-fit-source${clash.has(s.id) ? " is-clash" : ""}`}>
                      <span className="rc-fit-brand" lang="en">
                        {s.name}
                        {s.id === "mann" && mannBy && (
                          <span className="rc-fit-how">{t(mannBy === "vin" ? "fitment.by_vin" : "fitment.by_model")}</span>
                        )}
                      </span>
                      <span className="rc-fit-parts">
                        {(by[s.id] ?? []).map((p) =>
                          p.part === LIFETIME ? (
                            <span key={p.part} className="rc-fit-lifetime small">
                              {t("fitment.lifetime_short")}
                            </span>
                          ) : (
                            <PartChip key={p.part} part={p} />
                          )
                        )}
                      </span>
                    </div>
                  ))
                )}
                {(by.ufi_xref?.length ?? 0) > 0 && (
                  <div className="rc-fit-alt">
                    <span>{t("fitment.ufi_equivalents")}</span>
                    <span className="rc-fit-parts">
                      {by.ufi_xref!.map((p) => (
                        <PartChip key={p.part} part={p} quiet />
                      ))}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className="rc-fit-foot">{t("fitment.foot")}</p>
    </section>
  );
}

function PartChip({ part, quiet = false }: { part: FitmentPart; quiet?: boolean }) {
  return (
    <span className={`rc-fit-chip${quiet ? " quiet" : ""}`}>
      <bdi dir="ltr">{part.part}</bdi>
      <CopyButton value={part.part} label={part.part} />
    </span>
  );
}
