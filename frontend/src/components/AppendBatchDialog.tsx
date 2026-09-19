import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { apiErrorMessage, appendBatch, type AppendResult, type Dataset } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { IconArchive } from "./admin/AdminIcons";
import RecordKeyDialog from "./RecordKeyDialog";
import { IconClose } from "./SheetIcons";
import ErrorBanner from "./ErrorBanner";
import UploadDropzone from "./UploadDropzone";

/**
 * Adding a later file of the same shape to a dataset that already exists.
 *
 * The outcome is worth stating rather than just closing: "40 added, 12 replaced" is a
 * different thing from "52 added", and which one happened depends on whether the
 * dataset has a record key - so the dialog says up front which of the two it will be.
 */
export default function AppendBatchDialog({
  dataset,
  onClose,
}: {
  dataset: Dataset;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const qc = useQueryClient();
  const canSetKey = can("datasets.edit");
  const [keyOpen, setKeyOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AppendResult | null>(null);

  const hasKey = dataset.key_columns.length > 0;

  const upload = useMutation({
    mutationFn: (file: File) => appendBatch(dataset.id, file, undefined, setProgress),
    onSuccess: (outcome) => {
      setError(null);
      setResult(outcome);
      setProgress(0);
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["dataset", dataset.id] });
      qc.invalidateQueries({ queryKey: ["data", dataset.id] });
      qc.invalidateQueries({ queryKey: ["stats", dataset.id] });
      qc.invalidateQueries({ queryKey: ["group", dataset.id] });
      // The arrivals query is the one this dialog just changed the answer to, and it is
      // cached for a minute - so an explorer already open in another tab would show the
      // new rows with none of them marked, which reads as the marking being broken.
      qc.invalidateQueries({ queryKey: ["arrivals", dataset.id] });
    },
    onError: (e) => {
      setProgress(0);
      setError(apiErrorMessage(e, t("common.error_generic")));
    },
  });

  return createPortal(
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className="modal modal-sm"
        role="dialog"
        aria-modal="true"
        aria-label={t("append.title") ?? ""}
      >
        <header className="modal-head">
          <span className="modal-title">
            <IconArchive />
            {t("append.title")}
          </span>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label={t("common.close") ?? ""}
          >
            <IconClose />
          </button>
        </header>

        <div className="modal-body">
          <p className="muted">
            {t("append.same_columns", { columns: dataset.columns.length })}
          </p>
          {hasKey ? (
            <p className="muted">
              {t("append.will_replace", { columns: dataset.key_columns.join(" + ") })}
            </p>
          ) : (
            /* Stated as a caution with the remedy attached, rather than as a grey line
               of prose. The key is per dataset, so somebody who set one on another file
               has every reason to think this one is covered - and by the time the
               difference shows, the batch has already landed twice over. */
            <div className="append-warning" role="note">
              <p>{t("append.will_add_only")}</p>
              <p className="muted">{t("append.no_key_consequence")}</p>
              {canSetKey && (
                <button type="button" className="btn secondary" onClick={() => setKeyOpen(true)}>
                  {t("record_key.unset")}
                </button>
              )}
            </div>
          )}

          {result ? (
            <div className="append-result" role="status" aria-live="polite">
              <p>
                {t("append.added", { count: result.rows_added })}
                {result.rows_replaced > 0 &&
                  ` · ${t("append.replaced", { count: result.rows_replaced })}`}
              </p>
              <p className="muted">{t("append.now_holds", { count: result.row_count_raw })}</p>
              {result.cleaned_rebuilt && <p className="muted">{t("append.cleaned_rebuilt")}</p>}
            </div>
          ) : (
            <UploadDropzone
              onFile={(file) => upload.mutate(file)}
              busy={upload.isPending}
              progress={progress}
            />
          )}

          <ErrorBanner message={error} />
        </div>

        <footer className="modal-foot">
          <span style={{ flex: 1 }} />
          <button type="button" className="btn" onClick={onClose}>
            {result ? t("common.close") : t("filter.cancel")}
          </button>
        </footer>
      </div>

      {keyOpen && (
        <RecordKeyDialog
          dataset={dataset}
          columns={dataset.columns}
          onClose={() => setKeyOpen(false)}
        />
      )}
    </div>,
    document.body
  );
}
