import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { apiErrorMessage, appendBatch, type AppendResult, type Dataset } from "../api/client";
import { IconArchive } from "./admin/AdminIcons";
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
  const qc = useQueryClient();
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
          <p className={hasKey ? "muted" : "append-note"}>
            {hasKey
              ? t("append.will_replace", { columns: dataset.key_columns.join(" + ") })
              : t("append.will_add_only")}
          </p>

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
    </div>,
    document.body
  );
}
