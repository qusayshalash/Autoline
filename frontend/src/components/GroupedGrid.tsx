import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  fetchData,
  fetchGroups,
  groupPathFilters,
  type ColumnKind,
  type FilterRule,
} from "../api/client";
import { translateValue } from "../data/valueDictionary";
import GridCell from "./GridCell";

/** Rows loaded when a leaf group is expanded. Groups are usually small enough that this
 *  is the whole thing; when it isn't, the row shows how many are left. */
const LEAF_ROW_LIMIT = 200;
/** Sub-groups loaded per nested level. */
const SUBGROUP_LIMIT = 200;

export interface GroupedGridProps {
  datasetId: string;
  source: "raw" | "cleaned";
  groupBy: string[];
  filters: FilterRule[];
  search: string | null;
  /** columns rendered for leaf rows, in display order */
  visibleColumns: string[];
  /** index of each visible column within the full row tuple */
  visibleIndexes: number[];
  allColumns: string[];
  kindByColumn: Map<string, ColumnKind>;
  labelFor: (column: string) => string;
  /** top-level groups, already fetched by the page (so it can drive the pager) */
  topGroups: { value: string | null; count: number }[];
  /** columns whose values the user asked to see translated */
  translatedColumns: Set<string>;
}

export default function GroupedGrid(props: GroupedGridProps) {
  const { t } = useTranslation();
  const { groupBy, visibleColumns, labelFor, topGroups } = props;

  return (
    <table className="grouped-table">
      <thead>
        <tr>
          <th className="group-col">{t("group.column_header")}</th>
          {visibleColumns.map((c) => (
            <th key={c}>{labelFor(c)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {topGroups.map((g) => (
          <GroupNode
            key={String(g.value)}
            {...props}
            depth={0}
            path={[{ column: groupBy[0], value: g.value }]}
            count={g.count}
          />
        ))}
      </tbody>
    </table>
  );
}

interface NodeProps extends GroupedGridProps {
  depth: number;
  path: { column: string; value: string | null }[];
  count: number;
}

function GroupNode(props: NodeProps) {
  const { t } = useTranslation();
  const {
    datasetId,
    source,
    groupBy,
    filters,
    search,
    visibleColumns,
    visibleIndexes,
    allColumns,
    kindByColumn,
    depth,
    path,
    count,
  } = props;

  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const isLeafLevel = depth === groupBy.length - 1;
  const scopedFilters = [...filters, ...groupPathFilters(path)];
  const leaf = path[path.length - 1];
  // the group key still filters by the stored value; only what is printed changes
  const label =
    leaf.value !== null && props.translatedColumns.has(leaf.column)
      ? translateValue(leaf.value, i18n.language)
      : leaf.value;

  // sub-groups for the next grouping level
  const subQuery = useQuery({
    queryKey: ["group", datasetId, source, groupBy[depth + 1], scopedFilters, search],
    queryFn: () =>
      fetchGroups(datasetId, {
        column: groupBy[depth + 1],
        filters: scopedFilters,
        search,
        source,
        page_size: SUBGROUP_LIMIT,
      }),
    enabled: open && !isLeafLevel,
  });

  // actual rows once the deepest level is reached
  const rowQuery = useQuery({
    queryKey: ["group-rows", datasetId, source, scopedFilters, search],
    queryFn: () =>
      fetchData(datasetId, {
        page: 1,
        page_size: LEAF_ROW_LIMIT,
        filters: scopedFilters,
        search,
        source,
      }),
    enabled: open && isLeafLevel,
  });

  const busy = open && (subQuery.isFetching || rowQuery.isFetching);
  const failed = open && (subQuery.isError || rowQuery.isError);
  const colSpan = visibleColumns.length;

  return (
    <>
      <tr className={`group-row depth-${depth}`}>
        <td className="group-col">
          <button
            type="button"
            className="group-toggle"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            style={{ marginInlineStart: `${depth * 1.1}rem` }}
          >
            <svg
              className={open ? "group-chevron open" : "group-chevron"}
              width="10"
              height="10"
              viewBox="0 0 10 10"
              aria-hidden="true"
            >
              <path
                d="M3.5 2L7 5l-3.5 3"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="group-value">{label === null || label === "" ? "—" : label}</span>
            <span className="group-count">({count.toLocaleString()})</span>
          </button>
        </td>
        <td className="group-summary" colSpan={colSpan}>
          {busy && <span className="muted">{t("common.loading")}</span>}
          {/* an expanded group whose request failed would otherwise sit open and empty,
              which reads as "this group contains nothing" */}
          {!busy && failed && (
            <span className="group-failed">{t("common.error_loading_data")}</span>
          )}
        </td>
      </tr>

      {open && !isLeafLevel &&
        (subQuery.data?.groups ?? []).map((g) => (
          <GroupNode
            key={String(g.value)}
            {...props}
            depth={depth + 1}
            path={[...path, { column: groupBy[depth + 1], value: g.value }]}
            count={g.count}
          />
        ))}

      {open && !isLeafLevel && subQuery.data && subQuery.data.total_groups > subQuery.data.groups.length && (
        <tr className="group-more">
          <td colSpan={colSpan + 1}>
            {t("group.more_groups", {
              shown: subQuery.data.groups.length.toLocaleString(),
              total: subQuery.data.total_groups.toLocaleString(),
            })}
          </td>
        </tr>
      )}

      {open && isLeafLevel &&
        (rowQuery.data?.rows ?? []).map((row, i) => (
          <tr key={i} className="group-leaf-row">
            <td className="group-col" />
            {visibleIndexes.map((colIdx) => {
              const col = allColumns[colIdx];
              const kind = kindByColumn.get(col);
              const raw = String(row[colIdx] ?? "");
              const shown = props.translatedColumns.has(col)
                ? translateValue(raw, i18n.language)
                : raw;
              return (
                <td key={colIdx} className={`cell-${kind ?? "text"}`} title={raw}>
                  <GridCell value={shown} kind={kind} />
                </td>
              );
            })}
          </tr>
        ))}

      {open && isLeafLevel && rowQuery.data && rowQuery.data.total_rows > rowQuery.data.rows.length && (
        <tr className="group-more">
          <td colSpan={colSpan + 1}>
            {t("group.more_rows", {
              shown: rowQuery.data.rows.length.toLocaleString(),
              total: rowQuery.data.total_rows.toLocaleString(),
            })}
          </td>
        </tr>
      )}
    </>
  );
}
