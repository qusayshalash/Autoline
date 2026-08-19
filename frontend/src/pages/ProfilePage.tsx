import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import type { ColumnProfile, ProfileFinding } from "../api/client";
import { fetchColumnProfile, fetchProfileOverview } from "../api/client";
import Breadcrumb from "../components/Breadcrumb";
import ColumnKindIcon from "../components/ColumnKindIcon";
import QueryState from "../components/QueryState";
import { columnLabel } from "../data/columnDictionary";
import { translateValue } from "../data/valueDictionary";

/**
 * What is actually in each column.
 *
 * The import quality report answers "is this file sound?" once, for the file. This
 * answers "what is in this column?" as many times as somebody asks, and the split is the
 * whole design: the list of columns is one query, and the expensive per-column work only
 * happens for the column somebody opened.
 *
 * Fill is drawn as a bar because the useful judgement is proportional - a column that is
 * 43% populated is a different kind of problem from one that is 99.8% populated, and no
 * arrangement of digits makes that land as fast as two bars of different lengths.
 */
export default function ProfilePage() {
  const { datasetId = "" } = useParams();
  const { t, i18n } = useTranslation();
  const [selected, setSelected] = useState<string | null>(null);

  const overview = useQuery({
    queryKey: ["profile-overview", datasetId],
    queryFn: () => fetchProfileOverview(datasetId, "cleaned"),
  });

  if (overview.isLoading || overview.isError || !overview.data) {
    return (
      <QueryState
        loading={overview.isLoading}
        error={overview.isError ? overview.error : null}
        onRetry={overview.refetch}
      />
    );
  }

  const { total, columns } = overview.data;

  return (
    <div className="profile-page">
      <Breadcrumb
        items={[
          { label: t("nav.datasets"), to: "/" },
          { label: t("profile.title") },
        ]}
      />

      <header className="profile-head">
        <h1>{t("profile.title")}</h1>
        <p className="muted">
          {t("profile.subtitle", { rows: total.toLocaleString(i18n.language) })}
        </p>
      </header>

      <div className="profile-layout">
        <table className="profile-table">
          <thead>
            <tr>
              <th>{t("profile.column")}</th>
              <th>{t("profile.filled")}</th>
              <th className="num">{t("profile.distinct_approx")}</th>
              <th className="num">{t("profile.missing")}</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((c) => (
              <tr
                key={c.name}
                className={selected === c.name ? "is-selected" : undefined}
                onClick={() => setSelected(c.name)}
              >
                <th scope="row">
                  <button type="button" className="linkish">
                    {columnLabel(c.name, i18n.language)}
                  </button>
                </th>
                <td>
                  <span className="fill-bar" title={`${c.fill_pct}%`}>
                    <span
                      className={c.fill_pct < 50 ? "fill low" : "fill"}
                      style={{ width: `${Math.max(c.fill_pct, 0.5)}%` }}
                    />
                  </span>
                  <span className="fill-pct num">{c.fill_pct.toFixed(1)}%</span>
                </td>
                <td className="num">≈{c.approx_distinct.toLocaleString(i18n.language)}</td>
                <td className="num">
                  {c.missing ? c.missing.toLocaleString(i18n.language) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="profile-detail">
          {selected ? (
            <ColumnDetail datasetId={datasetId} column={selected} />
          ) : (
            <p className="muted profile-hint">{t("profile.pick_a_column")}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ColumnDetail({ datasetId, column }: { datasetId: string; column: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const q = useQuery({
    queryKey: ["profile-column", datasetId, column],
    queryFn: () => fetchColumnProfile(datasetId, column, "cleaned"),
  });

  if (q.isLoading || q.isError || !q.data) {
    return (
      <QueryState
        loading={q.isLoading}
        error={q.isError ? q.error : null}
        onRetry={q.refetch}
      />
    );
  }

  const p: ColumnProfile = q.data;
  const n = (v: number) => v.toLocaleString(lang);

  return (
    <section className="profile-card">
      <header>
        <h2>
          <ColumnKindIcon kind={p.kind} />
          {columnLabel(p.column, lang)}
        </h2>
        <span className="muted mono">{p.column}</span>
      </header>

      {p.findings.length > 0 && (
        <ul className="findings">
          {p.findings.map((f) => (
            <li key={f.code} className={f.level === "problem" ? "problem" : "note"}>
              {describe(f, t, lang)}
            </li>
          ))}
        </ul>
      )}

      <dl className="profile-stats">
        <div>
          <dt>{t("profile.filled")}</dt>
          <dd>
            {n(p.filled)} <span className="muted">({p.fill_pct.toFixed(1)}%)</span>
          </dd>
        </div>
        <div>
          <dt>{t("profile.distinct")}</dt>
          <dd>{n(p.distinct)}</dd>
        </div>
        <div>
          <dt>{t("profile.length_range")}</dt>
          <dd>
            {p.min_length === null
              ? "—"
              : p.min_length === p.max_length
                ? n(p.min_length)
                : `${n(p.min_length)} – ${n(p.max_length ?? 0)}`}
          </dd>
        </div>
        {p.zero_padded > 0 && (
          <div>
            <dt>{t("profile.zero_padded")}</dt>
            <dd>{n(p.zero_padded)}</dd>
          </div>
        )}
      </dl>

      {p.numeric && (
        <>
          <p className="drawer-section">{t("profile.numeric")}</p>
          <dl className="profile-stats">
            <div>
              <dt>{t("profile.min")}</dt>
              <dd className="num">{n(p.numeric.min)}</dd>
            </div>
            <div>
              <dt>{t("profile.median")}</dt>
              <dd className="num">{p.numeric.median === null ? "—" : n(p.numeric.median)}</dd>
            </div>
            <div>
              <dt>{t("profile.max")}</dt>
              <dd className="num">{n(p.numeric.max)}</dd>
            </div>
            <div>
              <dt>{t("profile.average")}</dt>
              <dd className="num">{p.numeric.avg === null ? "—" : n(p.numeric.avg)}</dd>
            </div>
          </dl>
        </>
      )}

      <p className="drawer-section">{t("profile.top_values")}</p>
      <ul className="value-list">
        {p.top_values.map((v, i) => (
          <li key={`${v.value}-${i}`}>
            <span className={v.blank ? "value blank" : "value"}>
              {v.blank ? t("statistics.unspecified") : translateValue(v.value, lang)}
            </span>
            <span className="value-bar">
              <span style={{ width: `${Math.max(v.pct, 0.5)}%` }} />
            </span>
            <span className="value-count num">{n(v.count)}</span>
            <span className="value-pct num muted">{v.pct.toFixed(1)}%</span>
          </li>
        ))}
      </ul>

      {p.lengths.length > 1 && (
        <>
          <p className="drawer-section">{t("profile.lengths")}</p>
          <ul className="value-list compact">
            {p.lengths.map((l) => (
              <li key={l.length}>
                <span className="value num">{n(l.length)}</span>
                <span className="value-bar">
                  <span style={{ width: `${Math.max(l.pct, 0.5)}%` }} />
                </span>
                <span className="value-count num">{n(l.count)}</span>
                <span className="value-pct num muted">{l.pct.toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="muted profile-timing">
        {t("profile.measured_in", { ms: Math.round(p.execution_ms) })}
      </p>
    </section>
  );
}

type Translate = ReturnType<typeof useTranslation>["t"];

/** Findings arrive as codes so they can be said in the reader's language. */
function describe(f: ProfileFinding, t: Translate, lang: string): string {
  return t(`profile.finding.${f.code}`, {
    count: (f.count ?? 0).toLocaleString(lang),
    pct: f.pct ?? 0,
    missing: (f.missing ?? 0).toLocaleString(lang),
    distinct: (f.distinct ?? 0).toLocaleString(lang),
    length: f.length ?? 0,
    low: Math.round(f.low ?? 0).toLocaleString(lang),
    high: Math.round(f.high ?? 0).toLocaleString(lang),
  });
}
