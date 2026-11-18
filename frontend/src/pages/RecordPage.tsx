import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { apiErrorMessage, fetchRecord, getDataset } from "../api/client";
import ErrorBanner from "../components/ErrorBanner";
import LoadingState from "../components/LoadingState";
import RecordCardView from "../components/RecordCardView";

/** One record, whole, reached from its row number in the grid. The card itself is
 *  RecordCardView, which the vehicle catalog shows too. */
export default function RecordPage() {
  const { t } = useTranslation();
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
        {record && (
          <button type="button" className="btn secondary" onClick={() => window.print()}>
            {t("record.print")}
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
        <RecordCardView record={record} source={dataset?.original_filename} />
      )}
    </div>
  );
}
