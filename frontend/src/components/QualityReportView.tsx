import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { QualityFinding, QualityReport } from "../api/client";
import { fetchQualityReport, getJob, startQualityReport } from "../api/client";

interface Props {
  datasetId: string;
  canRun: boolean;
}

/**
 * What the import actually did to the file.
 *
 * The point of this screen is that a successful import is not the same as a faithful
 * one: the transcoder substitutes bytes it cannot represent and the CSV reader is
 * lenient about malformed rows, and neither says so at the time. Everything here is
 * measured against the original upload, so "4,114,487 rows in the file, 4,114,487
 * loaded" is a real comparison rather than the database quoting itself.
 */
export default function QualityReportView({ datasetId, canRun }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: report, isLoading } = useQuery({
    queryKey: ["quality", datasetId],
    queryFn: () => fetchQualityReport(datasetId),
  });

  // The analysis reads the whole upload, so it runs as a job and is polled rather than
  // held open on a request.
  useEffect(() => {
    if (!jobId) return;
    let live = true;
    const tick = async () => {
      try {
        const job = await getJob(jobId);
        if (!live) return;
        setProgress(job.progress ?? "");
        if (job.status === "done") {
          setJobId(null);
          queryClient.invalidateQueries({ queryKey: ["quality", datasetId] });
          queryClient.invalidateQueries({ queryKey: ["datasets"] });
        } else if (job.status === "error") {
          setJobId(null);
          setError(job.error_message ?? t("common.error_generic"));
        }
      } catch {
        if (live) setJobId(null);
      }
    };
    const id = setInterval(tick, 1000);
    void tick();
    return () => {
      live = false;
      clearInterval(id);
    };
  }, [jobId, datasetId, queryClient, t]);

  async function run() {
    setError(null);
    try {
      const job = await startQualityReport(datasetId);
      setJobId(job.id);
      setProgress("");
    } catch {
      setError(t("common.error_generic"));
    }
  }

  const n = (v: number | null | undefined) => (v ?? 0).toLocaleString(lang);

  if (isLoading) return <p className="muted">{t("common.loading")}</p>;

  const running = !!jobId;

  return (
    <div className="quality">
      <div className="quality-actions">
        <button type="button" className="btn" onClick={run} disabled={running || !canRun}>
          {running ? t("quality.running") : report ? t("quality.rerun") : t("quality.run")}
        </button>
        {running && <ProgressNote progress={progress} />}
        {report && !running && (
          <span className="muted quality-generated">
            {t("quality.generated", {
              when: new Date(report.generated_at).toLocaleString(lang),
              seconds: (report.duration_ms / 1000).toFixed(1),
            })}
          </span>
        )}
      </div>

      {error && <p className="quality-error">{error}</p>}

      {!report && !running && <p className="muted">{t("quality.none_yet")}</p>}

      {report && (
        <>
          <Verdict report={report} />
          <Numbers report={report} n={n} />
          {report.encoding_issues.damaged_values > 0 && <Damage report={report} n={n} />}
          <Findings findings={report.findings} />
          <ColumnTable report={report} n={n} />
        </>
      )}
    </div>
  );
}

function ProgressNote({ progress }: { progress: string }) {
  const { t, i18n } = useTranslation();
  const [phase, value] = progress.split(":");
  if (phase === "scanning" && value && /^\d+$/.test(value)) {
    return (
      <span className="muted">
        {t("quality.progress_rows", { count: Number(value).toLocaleString(i18n.language) })}
      </span>
    );
  }
  const key =
    phase === "profiling"
      ? "quality.progress_profiling"
      : value === "bytes"
        ? "quality.progress_bytes"
        : "quality.progress_records";
  return <span className="muted">{t(key)}</span>;
}

function Verdict({ report }: { report: QualityReport }) {
  const { t } = useTranslation();
  return (
    <div className={`quality-verdict verdict-${report.verdict}`}>
      <strong>{t(`quality.verdict.${report.verdict}`)}</strong>
      <span>{t(`quality.verdict_hint.${report.verdict}`)}</span>
    </div>
  );
}

function Numbers({ report, n }: { report: QualityReport; n: (v: number | null) => string }) {
  const { t } = useTranslation();
  const inFile = report.rows.in_file;
  const dropped = inFile === null ? null : inFile - report.rows.loaded;

  return (
    <div className="quality-grid">
      <Figure label={t("quality.rows_in_file")} value={inFile === null ? "—" : n(inFile)} />
      <Figure label={t("quality.rows_loaded")} value={n(report.rows.loaded)} />
      <Figure
        label={t("quality.rows_dropped")}
        value={dropped === null ? "—" : n(dropped)}
        tone={dropped ? "bad" : "good"}
      />
      <Figure
        label={t("quality.damaged_values")}
        value={n(report.encoding_issues.damaged_values)}
        tone={report.encoding_issues.damaged_values ? "warn" : "good"}
      />
      <Figure label={t("quality.columns")} value={n(report.structure.columns)} />
      <Figure
        label={t("quality.duplicate_rows")}
        value={n(report.rows.duplicates)}
        tone={report.rows.duplicates ? "warn" : "good"}
      />
      <Figure
        label={t("quality.encoding")}
        value={`${report.source_file.encoding} · ${report.source_file.delimiter}`}
      />
      <Figure
        label={t("quality.row_shape")}
        value={Object.entries(report.structure.field_count_spread)
          .map(([width, count]) => `${width} × ${n(count)}`)
          .join(" · ")}
      />
    </div>
  );
}

function Figure({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "warn" | "bad";
}) {
  return (
    <div className={tone ? `quality-figure tone-${tone}` : "quality-figure"}>
      <span className="quality-figure-label">{label}</span>
      <strong className="quality-figure-value">{value}</strong>
    </div>
  );
}

function Damage({ report, n }: { report: QualityReport; n: (v: number | null) => string }) {
  const { t } = useTranslation();
  return (
    <section className="quality-damage">
      <h4>{t("quality.damage_title")}</h4>
      <p className="muted">
        {t("quality.damage_hint", {
          encoding: report.source_file.encoding,
          count: n(report.encoding_issues.undecodable_bytes),
        })}
      </p>
      <div className="quality-table-wrap">
        <table className="quality-table">
          <thead>
            <tr>
              <th>{t("quality.record")}</th>
              <th>{t("quality.column")}</th>
              <th>{t("quality.stored_value")}</th>
              <th>{t("quality.byte")}</th>
              <th>{t("quality.offset")}</th>
            </tr>
          </thead>
          <tbody>
            {report.encoding_issues.samples.map((d) => (
              <tr key={`${d.row}-${d.column}-${d.byte_offset}`}>
                <td className="num">{n(d.row)}</td>
                <td>{d.column}</td>
                <td className="mono">{d.value}</td>
                <td className="mono">{d.byte}</td>
                <td className="num mono">{n(d.byte_offset)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {report.encoding_issues.damaged_values > report.encoding_issues.samples.length && (
        <p className="muted">
          {t("quality.damage_truncated", {
            shown: n(report.encoding_issues.samples.length),
            total: n(report.encoding_issues.damaged_values),
          })}
        </p>
      )}
    </section>
  );
}

function Findings({ findings }: { findings: QualityFinding[] }) {
  const { t, i18n } = useTranslation();
  if (findings.length === 0) return null;
  const order = { problem: 0, warning: 1, info: 2 } as const;
  const sorted = [...findings].sort((a, b) => order[a.level] - order[b.level]);

  return (
    <section className="quality-findings">
      <h4>{t("quality.findings")}</h4>
      <ul>
        {sorted.map((f, i) => (
          <li key={`${f.code}-${f.column ?? i}`} className={`finding-${f.level}`}>
            <span className="finding-dot" />
            <span>
              {t(`quality.finding.${f.code}`, {
                count: (f.count ?? 0).toLocaleString(i18n.language),
                column: f.column ?? "",
                expected: f.expected ?? 0,
                in_file: (f.in_file ?? 0).toLocaleString(i18n.language),
                loaded: (f.loaded ?? 0).toLocaleString(i18n.language),
                bytes: f.bytes ?? 0,
                pct: f.pct ?? 0,
                defaultValue: f.code,
              })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ColumnTable({ report, n }: { report: QualityReport; n: (v: number | null) => string }) {
  const { t } = useTranslation();
  return (
    <section className="quality-columns">
      <h4>{t("quality.column_profile")}</h4>
      <div className="quality-table-wrap">
        <table className="quality-table">
          <thead>
            <tr>
              <th>{t("quality.column")}</th>
              <th className="num">{t("quality.fill")}</th>
              <th className="num">{t("quality.missing")}</th>
              <th className="num">{t("quality.distinct")}</th>
              <th className="num">{t("quality.length")}</th>
            </tr>
          </thead>
          <tbody>
            {report.columns.map((c) => (
              <tr key={c.name}>
                <td className="mono">{c.name}</td>
                <td className="num">
                  <span className="quality-fill">
                    <span className="quality-fill-bar">
                      <span style={{ width: `${c.fill_pct}%` }} />
                    </span>
                    {c.fill_pct.toFixed(c.fill_pct === 100 ? 0 : 2)}%
                  </span>
                </td>
                <td className="num">{n(c.missing)}</td>
                <td className="num">{n(c.distinct)}</td>
                <td className="num">
                  {c.min_length === null ? "—" : `${c.min_length}–${c.max_length}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
