import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ColumnKind } from "../api/client";
import GridCell from "./GridCell";
import { IconReset } from "./SheetIcons";

/**
 * A grid cell that can be corrected in place.
 *
 * The interaction is the one the app already uses to rename a file: click to open,
 * Enter to commit, Escape to abandon, blur to commit. Nothing new to learn, and no
 * dialog between the reader and the value they are looking at.
 *
 * A corrected cell is marked, and its tooltip carries what the file itself said. That
 * is the part that matters: a correction is a claim that the source is wrong, and
 * anybody reading the table afterwards is entitled to see both.
 */
export default function EditableCell({
  value,
  shown,
  kind,
  editable,
  correctedFrom,
  onCommit,
  onRevert,
  columnLabel,
}: {
  /** the stored value, which is what an edit starts from */
  value: string;
  /** what to display - the same thing, unless the column's values are translated */
  shown: string;
  kind?: ColumnKind;
  editable: boolean;
  /** the file's own value, when this cell has been corrected */
  correctedFrom?: string | null;
  onCommit: (next: string) => void;
  /** Puts the file's own value back. Only offered on a cell that has been corrected. */
  onRevert: () => void;
  columnLabel: string;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  // A page change or a sort reuses this component for a different row, so the draft has
  // to follow the value rather than survive it - otherwise an abandoned edit reappears
  // on an unrelated record.
  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  function commit() {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="cell-editor"
        value={draft}
        aria-label={columnLabel}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") {
            setDraft(value);
            setEditing(false);
          }
        }}
      />
    );
  }

  const corrected = correctedFrom != null;
  const title = corrected
    ? t("corrections.was", { value: correctedFrom || "—" })
    : value;

  if (!editable) {
    return (
      <span className={corrected ? "cell-corrected" : undefined} title={title}>
        <GridCell value={shown} kind={kind} />
      </span>
    );
  }

  return (
    <span className="cell-edit-wrap">
      <button
        type="button"
        className={`cell-edit${corrected ? " cell-corrected" : ""}`}
        title={title}
        aria-label={t("corrections.edit_cell", { column: columnLabel })}
        onClick={() => setEditing(true)}
      >
        <GridCell value={shown} kind={kind} />
      </button>
      {corrected && (
        <button
          type="button"
          className="cell-revert"
          onClick={onRevert}
          title={t("corrections.revert_to", { value: correctedFrom || "—" }) ?? ""}
          aria-label={t("corrections.revert_cell", { column: columnLabel }) ?? ""}
        >
          <IconReset />
        </button>
      )}
    </span>
  );
}
