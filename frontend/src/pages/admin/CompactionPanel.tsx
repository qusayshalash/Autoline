import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { CompactionResult } from "../../api/admin";
import { fetchCompactionEstimate, startCompaction } from "../../api/admin";
import { apiErrorMessage, getJob, listDatasets } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconDatabase } from "../../components/admin/AdminIcons";
import { AdminPanel, formatBytes } from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";

const POLL_MS = 800;

/**
 * Reclaiming the free space inside each dataset's file.
 *
 * The button is per-file rather than a single "compact everything", because each run
 * rewrites gigabytes and briefly holds that file's write lock; doing them one at a time
 * is both the honest presentation and the safe one.
 */
export default function CompactionPanel() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [error, setError] = useState<string | null>(null);

  const { data: files } = useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
  const ready = (files ?? []).filter((f) => f.status === "ready");

  if (!can("datasets.delete") || ready.length === 0) return null;

  return (
    <AdminPanel icon={<IconDatabase />} title={t("admin.compaction.title")}>
      <ErrorBanner message={error} />
      <p className="muted admin-note">{t("admin.compaction.hint")}</p>
      {ready.map((f) => (
        <CompactionRow key={f.id} datasetId={f.id} name={f.original_filename} onError={setError} />
      ))}
    </AdminPanel>
  );
}

function CompactionRow({
  datasetId,
  name,
  onError,
}: {
  datasetId: string;
  name: string;
  onError: (message: string | null) => void;
}) {
  const { t } = useTranslation();
  const [progress, setProgress] = useState<string | null>(null);
  const [done, setDone] = useState<CompactionResult | null>(null);
  const timer = useRef<number | null>(null);

  const { data: estimate, refetch } = useQuery({
    queryKey: ["compaction-estimate", datasetId],
    queryFn: () => fetchCompactionEstimate(datasetId),
  });

  // the poll stops with the component; the job itself is on the server and finishes
  // either way
  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
  }, []);

  async function run() {
    onError(null);
    setDone(null);
    setProgress(t("admin.compaction.running"));
    try {
      const job = await startCompaction(datasetId);
      timer.current = window.setInterval(async () => {
        try {
          const state = await getJob(job.id);
          setProgress(describe(state.progress, t));
          if (state.status === "done" || state.status === "error") {
            if (timer.current) window.clearInterval(timer.current);
            timer.current = null;
            setProgress(null);
            if (state.status === "error") {
              onError(state.error_message || t("admin.compaction.failed"));
            } else {
              setDone(state.result as unknown as CompactionResult);
              refetch();
            }
          }
        } catch (e) {
          if (timer.current) window.clearInterval(timer.current);
          timer.current = null;
          setProgress(null);
          onError(apiErrorMessage(e, t("common.error_generic")));
        }
      }, POLL_MS);
    } catch (e) {
      setProgress(null);
      onError(apiErrorMessage(e, t("common.error_generic")));
    }
  }

  return (
    <div className="compaction-row">
      <span className="compaction-name mono wrap">{name}</span>
      <span className="compaction-size">
        {estimate ? formatBytes(estimate.file_bytes) : "—"}
      </span>
      <span className="compaction-action">
        {progress ? (
          <span className="backup-progress">{progress}</span>
        ) : (
          <button type="button" className="btn secondary small" onClick={run}>
            {t("admin.compaction.run")}
          </button>
        )}
      </span>
      {done && (
        <span className="compaction-result">
          {done.skipped
            ? t("admin.compaction.already_compact")
            : t("admin.compaction.freed", {
                size: formatBytes(done.freed_bytes),
                before: formatBytes(done.bytes_before),
                after: formatBytes(done.bytes_after),
              })}
        </span>
      )}
    </div>
  );
}

type Translate = ReturnType<typeof useTranslation>["t"];

/** Job progress is a machine word; this is what it means on screen. */
function describe(progress: string, t: Translate): string {
  const known = ["writing", "verifying", "swapping"];
  return known.includes(progress)
    ? t(`admin.compaction.progress_${progress}`)
    : t("admin.compaction.running");
}
