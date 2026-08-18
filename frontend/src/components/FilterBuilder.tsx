import { useTranslation } from "react-i18next";

import { newFilter, type ColumnKind, type FilterOp, type FilterRule } from "../api/client";
import { columnLabel } from "../data/columnDictionary";
import ColumnSelect from "./ColumnSelect";
import { IconTrash } from "./SheetIcons";
import ValueAutocomplete from "./ValueAutocomplete";

const OPS: FilterOp[] = [
  "eq",
  "neq",
  "starts_with",
  "contains",
  "ends_with",
  "gt",
  "gte",
  "lt",
  "lte",
  "is_null",
  "not_null",
];
const NO_VALUE_OPS = new Set<FilterOp>(["is_null", "not_null"]);

interface Props {
  columns: string[];
  filters: FilterRule[];
  onChange: (filters: FilterRule[]) => void;
  /** hide the built-in "+ Add filter" button when the caller renders its own */
  hideAddButton?: boolean;
  /** "dialog" adds Where/And conjunction labels and an icon delete button. The rule
   *  editing itself is identical in both variants - only the chrome differs. */
  variant?: "inline" | "dialog";
  /** Supply these to offer the column's real values as suggestions in the value box.
   *  Without them the value stays a plain free-text field. */
  datasetId?: string;
  source?: "raw" | "cleaned";
  /** used for the type icons in the dialog variant's column picker */
  kindByColumn?: Map<string, ColumnKind>;
}

export default function FilterBuilder({
  columns,
  filters,
  onChange,
  hideAddButton = false,
  variant = "inline",
  datasetId,
  source = "cleaned",
  kindByColumn,
}: Props) {
  const { t, i18n } = useTranslation();
  const isDialog = variant === "dialog";

  function update(index: number, patch: Partial<FilterRule>) {
    const next = filters.slice();
    next[index] = { ...next[index], ...patch };
    onChange(next);
  }

  function remove(index: number) {
    onChange(filters.filter((_, i) => i !== index));
  }

  function add() {
    onChange([...filters, newFilter(columns)]);
  }

  return (
    <div>
      {filters.map((f, i) => (
        <div className={isDialog ? "filter-row filter-row-dialog" : "filter-row"} key={i}>
          {isDialog && (
            <span className="filter-conjunction">{i === 0 ? t("filter.where") : t("filter.and")}</span>
          )}
          {isDialog ? (
            <ColumnSelect
              columns={columns}
              value={f.column}
              kindByColumn={kindByColumn}
              onChange={(c) => update(i, { column: c })}
            />
          ) : (
            <select value={f.column} onChange={(e) => update(i, { column: e.target.value })}>
              {columns.map((c) => (
                // the option's value stays the real column name - only the text is localised
                <option key={c} value={c}>
                  {columnLabel(c, i18n.language)}
                </option>
              ))}
            </select>
          )}
          <select value={f.op} onChange={(e) => update(i, { op: e.target.value as FilterOp })}>
            {OPS.map((op) => (
              <option key={op} value={op}>
                {t(`cleaning.op_${op}`)}
              </option>
            ))}
          </select>
          {!NO_VALUE_OPS.has(f.op) &&
            (datasetId && f.column ? (
              <ValueAutocomplete
                datasetId={datasetId}
                source={source}
                column={f.column}
                value={String(f.value ?? "")}
                onChange={(v) => update(i, { value: v })}
                placeholder={t("cleaning.value") ?? ""}
              />
            ) : (
              <input
                type="text"
                placeholder={t("cleaning.value") ?? ""}
                value={f.value ?? ""}
                onChange={(e) => update(i, { value: e.target.value })}
              />
            ))}
          {isDialog ? (
            <button
              className="icon-btn danger"
              type="button"
              onClick={() => remove(i)}
              aria-label={t("cleaning.remove")}
              title={t("cleaning.remove") ?? ""}
            >
              <IconTrash />
            </button>
          ) : (
            <button className="btn danger" type="button" onClick={() => remove(i)}>
              {t("cleaning.remove")}
            </button>
          )}
        </div>
      ))}
      {!hideAddButton && (
        <button className="btn secondary" type="button" onClick={add} disabled={columns.length === 0}>
          + {t("cleaning.add_filter")}
        </button>
      )}
    </div>
  );
}
