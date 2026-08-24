import { useTranslation } from "react-i18next";

import type { StatisticsOut } from "../../api/statistics";
import { IconSpark } from "./StatsIcons";
import { formatCount, formatPercent } from "./labels";
import type { ChartRow } from "./rows";

/** Hebrew token marking a fuel value as electrified: "חשמל" alone is electric, and the
 *  hybrids are written "חשמל/בנזין" and "חשמל/דיזל". Nothing else in this column
 *  contains it, so one token identifies the whole group. */
const ELECTRIC_TOKEN = "חשמל";

/** The share the leading values have to reach before the note reports how few of them it
 *  took. Three quarters is high enough that reaching it early is genuinely a
 *  concentration, and low enough to be reached before the truncation cut on most
 *  columns. */
const PARETO_TARGET = 75;

interface Props {
  stats: StatisticsOut;
  rows: ChartRow[];
  /** the manufacturer the filters pin down, when they pin one down */
  subject?: string;
}

/**
 * Sentences read straight off the numbers already on screen.
 *
 * Every note restates a figure the user can verify in the table below it - a leading
 * share, a concentration, a gap in the data. Nothing is inferred, predicted or compared
 * against anything the file doesn't contain, because a dashboard that editorialises is
 * one the reader has to second-guess.
 */
export default function InsightNotes({ stats, rows, subject }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const real = rows.filter((r) => !r.other && !r.unspecifiedRow);
  if (stats.total === 0 || real.length === 0) return null;

  const notes: string[] = [];
  const of = subject ?? t("statistics.subject_matching");

  const top = real[0];
  if (top) {
    notes.push(
      t("statistics.note_leading", {
        share: formatPercent(top.percentage, lang),
        subject: of,
        value: top.label,
      })
    );
  }

  if (real.length >= 3) {
    const three = real.slice(0, 3);
    notes.push(
      t("statistics.note_concentration", {
        count: 3,
        share: formatPercent(
          three.reduce((a, r) => a + r.percentage, 0),
          lang
        ),
        values: three.map((r) => r.label).join(t("statistics.list_separator")),
      })
    );
  }

  // How concentrated the column is: how few values it takes to account for most of the
  // data. Worth saying only when there are enough distinct values for that to be a
  // finding rather than an artefact of having four categories, and only for value
  // breakdowns - on a date axis the buckets are ordered by time, so a run down the list
  // is not a ranking.
  //
  // Accumulated here over the real values alone rather than reused from the table
  // column, which runs over every row including the unspecified bucket. Counting blanks
  // towards "N values cover X%" would credit the values with reach they do not have.
  if (stats.mode === "value" && stats.distinct_values >= 10) {
    let covered = 0;
    let needed = 0;
    for (const r of real) {
      covered += r.count;
      needed += 1;
      if (stats.total > 0 && (covered * 100) / stats.total >= PARETO_TARGET) break;
    }
    const reach = stats.total > 0 ? (covered * 100) / stats.total : 0;

    if (reach >= PARETO_TARGET) {
      notes.push(
        t("statistics.note_pareto", {
          count: formatCount(needed, lang),
          distinct: formatCount(stats.distinct_values, lang),
          share: formatPercent(reach, lang),
          subject: of,
        })
      );
    } else if (stats.truncated) {
      // The listed values never reach the target, so the honest statement is the one
      // the table can actually support: this is how far the whole visible run gets, and
      // the rest of the data is spread across values too thin to be listed. This is the
      // shape a diffuse column has, and saying so is the finding.
      notes.push(
        t("statistics.note_pareto_diffuse", {
          count: formatCount(needed, lang),
          distinct: formatCount(stats.distinct_values, lang),
          share: formatPercent(reach, lang),
          subject: of,
        })
      );
    }
  }

  // Only meaningful when the breakdown is by fuel; on any other column no value carries
  // the token and the note is simply not produced.
  const electrified = rows.filter((r) => r.rawValue.includes(ELECTRIC_TOKEN));
  if (electrified.length > 0) {
    const share = electrified.reduce((a, r) => a + r.percentage, 0);
    const count = electrified.reduce((a, r) => a + r.count, 0);
    notes.push(
      t("statistics.note_electrified", {
        share: formatPercent(share, lang),
        count: formatCount(count, lang),
        subject: of,
      })
    );
  }

  const unspecified = rows.find((r) => r.unspecifiedRow);
  if (unspecified && unspecified.percentage >= 1) {
    notes.push(
      t("statistics.note_unspecified", {
        share: formatPercent(unspecified.percentage, lang),
        count: formatCount(unspecified.count, lang),
      })
    );
  }

  if (stats.truncated) {
    notes.push(
      t("statistics.note_truncated", {
        shown: formatCount(real.length, lang),
        total: formatCount(stats.distinct_values, lang),
      })
    );
  }

  if (notes.length === 0) return null;

  return (
    <section className="stats-notes">
      <h3>
        <IconSpark />
        {t("statistics.insights")}
      </h3>
      <ul>
        {notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </section>
  );
}
