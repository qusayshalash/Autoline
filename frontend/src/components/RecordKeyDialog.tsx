import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import {
  apiErrorMessage,
  checkDatasetKey,
  clearDatasetKey,
  setDatasetKey,
  type ColumnKind,
  type Dataset,
} from "../api/client";
import { IconKey } from "./admin/AdminIcons";
import { IconClose, IconPlusCircle, IconTrash } from "./SheetIcons";
import ColumnSelect from "./ColumnSelect";
import ErrorBanner from "./ErrorBanner";

const MAX_COLUMNS = 4;

/**
 * Choosing the columns that identify a record.
 *
 * Nothing in an imported table identifies a row: every column is text, there is no key,
 * and row order is not stable across a re-import. So this is asked rather than guessed -
 * and checked rather than believed. The count comes back before anything is saved,
 * because "12 records share this value" is what tells someone to add another column or
 * to remove the duplicates first; a bare refusal tells them nothing.
 */
export default function RecordKeyDialog({
  dataset,
  columns,
  kindByColumn,
  onClose,
}: {
  dataset: Dataset;
  columns: string[];
  kindByColumn?: Map<string, ColumnKind>;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<string[]>(
    dataset.key_columns.length ? dataset.key_columns : columns.slice(0, 1)
  );
  const [error, setError] = useState<string | null>(null);

  const n = (value: number) => value.toLocaleString(i18n.language);

  // The check runs as the choice changes rather than behind a button: the whole value
  // of it is seeing the answer while still deciding.
  const check = useQuery({
    queryKey: ["dataset-key-check", dataset.id, draft],
    queryFn: () => checkDatasetKey(dataset.id, draft),
    enabled: draft.length > 0,
    retry: false,
  });

  function done() {
    qc.invalidateQueries({ queryKey: ["dataset", dataset.id] });
    qc.invalidateQueries({ queryKey: ["datasets"] });
    onClose();
  }

  const save = useMutation({
    mutationFn: () => setDatasetKey(dataset.id, draft),
    onSuccess: done,
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const clear = useMutation({
    mutationFn: () => clearDatasetKey(dataset.id),
    onSuccess: done,
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  function availableFor(index: number): string[] {
    const taken = new Set(draft.filter((_, i) => i !== index));
    return columns.filter((c) => !taken.has(c));
  }

  const firstFree = columns.find((c) => !draft.includes(c));
  const result = check.data;

  return createPortal(
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className="modal modal-sm"
        role="dialog"
        aria-modal="true"
        aria-label={t("record_key.title") ?? ""}
      >
        <header className="modal-head">
          <span className="modal-title">
            <IconKey />
            {t("record_key.title")}
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
          <p className="muted">{t("record_key.explain")}</p>

          {draft.map((column, i) => (
            <div className="filter-row filter-row-dialog" key={i}>
              <span className="filter-conjunction">
                {i === 0 ? t("record_key.by") : t("record_key.and")}
              </span>
              <ColumnSelect
                columns={availableFor(i)}
                value={column}
                kindByColumn={kindByColumn}
                onChange={(next) => setDraft((prev) => prev.map((c, j) => (j === i ? next : c)))}
              />
              {draft.length > 1 && (
                <button
                  type="button"
                  className="icon-btn danger"
                  onClick={() => setDraft((prev) => prev.filter((_, j) => j !== i))}
                  aria-label={t("cleaning.remove") ?? ""}
                  title={t("cleaning.remove") ?? ""}
                >
                  <IconTrash />
                </button>
              )}
            </div>
          ))}

          <button
            type="button"
            className="link-btn"
            onClick={() => firstFree && setDraft([...draft, firstFree])}
            disabled={!firstFree || draft.length >= MAX_COLUMNS}
          >
            <IconPlusCircle />
            {t("record_key.add_column")}
          </button>

          <div className="key-verdict" role="status" aria-live="polite">
            {check.isFetching && <span className="muted">{t("record_key.checking")}</span>}
            {!check.isFetching && check.isError && (
              <span className="key-verdict-bad">
                {apiErrorMessage(check.error, t("common.error_generic"))}
              </span>
            )}
            {!check.isFetching && result?.unique && (
              <span className="key-verdict-good">
                {t("record_key.unique", {
                  count: result.distinct_keys,
                  total: n(result.total_rows),
                })}
              </span>
            )}
            {!check.isFetching && result && !result.unique && (
              <span className="key-verdict-bad">
                {result.blank_keys > 0
                  ? t("record_key.blank", { count: result.blank_keys })
                  : t("record_key.repeated", { count: result.duplicate_rows })}
              </span>
            )}
          </div>

          <ErrorBanner message={error} />
        </div>

        <footer className="modal-foot">
          {dataset.key_columns.length > 0 && (
            <button
              type="button"
              className="btn secondary"
              onClick={() => clear.mutate()}
              disabled={clear.isPending}
            >
              {t("record_key.clear")}
            </button>
          )}
          <span style={{ flex: 1 }} />
          <button type="button" className="btn secondary" onClick={onClose}>
            {t("filter.cancel")}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => save.mutate()}
            disabled={!result?.unique || save.isPending}
          >
            {t("record_key.save")}
          </button>
        </footer>
      </div>
    </div>,
    document.body
  );
}
