import { useTranslation } from "react-i18next";

import { type VinCheck, type VinReading } from "../api/client";
import { translateValue } from "../data/valueDictionary";

/**
 * The vehicle's chassis number, read: its seventeen characters split into the parts the
 * standard gives them, and each part the registry can vouch for checked against the
 * record - the make, the model code, the model year, the check digit.
 *
 * Which checks apply to which maker was measured on the registry, not assumed (backend
 * app/services/vin.py): Toyota, for one, does not put the year in character 10 for cars
 * sold here, so a Toyota's year is shown as "not encoded by this maker" rather than
 * judged. Red is kept for the one finding that means "this number is not this car's":
 * a make its prefix does not belong to.
 */

/** The parts, in the number's own left-to-right order: [first, last] character, 1-based. */
const PARTS: { id: string; from: number; to: number }[] = [
  { id: "maker", from: 1, to: 3 },
  { id: "model", from: 4, to: 8 },
  { id: "check", from: 9, to: 9 },
  { id: "year", from: 10, to: 10 },
  { id: "plant", from: 11, to: 11 },
  { id: "serial", from: 12, to: 17 },
];

export default function VinPanel({ reading }: { reading: VinReading }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  if (!reading.standard) {
    return (
      <section className="rc-section rc-vin is-nonstandard" aria-labelledby="rc-vin-title">
        <h2 id="rc-vin-title" className="rc-section-title">
          {t("vin.title")}
        </h2>
        <p className="rc-note">{t("vin.nonstandard")}</p>
      </section>
    );
  }

  const chars = reading.vin.split("");
  const maker = reading.maker;
  const makeName = (value?: string | number | null) =>
    value ? translateValue(String(value), lang) : "—";
  const issues: string[] = [];
  if (maker?.state === "mismatch") {
    issues.push(
      t("vin.issue_maker", {
        wmi: reading.wmi,
        expected: makeName(maker.makes?.[0]),
        registry: makeName(maker.registry),
      })
    );
  }
  if (reading.year?.state === "mismatch") {
    issues.push(t("vin.issue_year", { decoded: reading.year.decoded, registry: reading.year.registry }));
  }
  if (reading.model?.state === "mismatch") {
    issues.push(t("vin.issue_model", { code: reading.model_code, registry: reading.model.registry }));
  }
  if (reading.check_digit?.state === "invalid") {
    issues.push(t("vin.issue_check"));
  }

  return (
    <section className={`rc-section rc-vin verdict-${reading.verdict}`} aria-labelledby="rc-vin-title">
      <div className="rc-vin-head">
        <h2 id="rc-vin-title" className="rc-section-title">
          {t("vin.title")}
        </h2>
        <span className={`rc-vin-verdict ${reading.verdict}`}>{t(`vin.verdict_${reading.verdict}`)}</span>
      </div>

      {/* the number as it is written: always left to right, whatever the page */}
      <div className="rc-vin-chars" dir="ltr" aria-label={reading.vin}>
        {PARTS.map((part) => (
          <div key={part.id} className={`rc-vin-part p-${part.id}`}>
            <div className="rc-vin-boxes">
              {chars.slice(part.from - 1, part.to).map((c, i) => (
                <span key={i} className={`rc-vin-ch${wrong(part.id, reading) ? " is-wrong" : ""}`}>
                  {c}
                </span>
              ))}
            </div>
            <span className="rc-vin-pos">{part.from === part.to ? part.from : `${part.from}–${part.to}`}</span>
          </div>
        ))}
      </div>

      <div className="rc-vin-legend">
        <Fact
          part="maker"
          label={t("vin.part_maker")}
          value={reading.known ? makeName(maker?.makes?.[0]) : t("vin.unknown_prefix")}
          check={maker}
          ok={t("vin.ok_maker")}
        />
        <Fact
          part="model"
          label={t("vin.part_model")}
          value={reading.model_code ?? "—"}
          code
          check={reading.model}
          ok={t("vin.ok_model")}
        />
        <Fact
          part="year"
          label={t("vin.part_year")}
          value={reading.year?.decoded != null ? String(reading.year.decoded) : "—"}
          check={reading.year}
          ok={t("vin.ok_year")}
          near={t("vin.near_year")}
          unchecked={reading.known ? t("vin.year_not_encoded") : undefined}
        />
        {reading.check_digit && reading.check_digit.state !== "unchecked" && (
          <Fact
            part="check"
            label={t("vin.part_check")}
            value={reading.check_digit.code ?? "—"}
            code
            check={reading.check_digit}
            ok={t("vin.ok_check")}
          />
        )}
        <Fact part="serial" label={t("vin.part_serial")} value={reading.serial ?? "—"} code />
      </div>

      {issues.length > 0 && (
        <div className={`rc-vin-alert ${reading.verdict}`} role={reading.verdict === "bad" ? "alert" : undefined}>
          <strong>{t(reading.verdict === "bad" ? "vin.alert_bad" : "vin.alert_warn")}</strong>
          <ul>
            {issues.map((text, i) => (
              <li key={i}>
                <bdi>{text}</bdi>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** Whether a part's characters are the ones that disagree with the record. */
function wrong(part: string, reading: VinReading): boolean {
  if (part === "maker") return reading.maker?.state === "mismatch";
  if (part === "model") return reading.model?.state === "mismatch";
  if (part === "year") return reading.year?.state === "mismatch";
  if (part === "check") return reading.check_digit?.state === "invalid";
  return false;
}

function Fact({
  part,
  label,
  value,
  code = false,
  check,
  ok,
  near,
  unchecked,
}: {
  part: string;
  label: string;
  value: string;
  code?: boolean;
  check?: VinCheck | null;
  ok?: string;
  near?: string;
  unchecked?: string;
}) {
  const { t } = useTranslation();
  const state = check?.state;
  const note =
    state === "match" || state === "valid"
      ? { tone: "ok", text: `✓ ${ok}` }
      : state === "near"
        ? { tone: "ok", text: `✓ ${near}` }
        : state === "mismatch" || state === "invalid"
          ? { tone: "bad", text: `✗ ${t("vin.differs")}` }
          : unchecked
            ? { tone: "muted", text: unchecked }
            : null;

  return (
    <div className={`rc-vin-fact p-${part}`}>
      <span className="rc-vin-swatch" aria-hidden="true" />
      <span className="rc-vin-label">{label}</span>
      <span className="rc-vin-value">{code ? <bdi dir="ltr">{value}</bdi> : <bdi>{value}</bdi>}</span>
      {note && <span className={`rc-vin-note ${note.tone}`}>{note.text}</span>}
    </div>
  );
}
