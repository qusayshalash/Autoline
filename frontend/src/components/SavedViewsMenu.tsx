import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  apiErrorMessage,
  createSavedView,
  deleteSavedView,
  listSavedViews,
  updateSavedView,
  type SavedView,
  type ViewState,
} from "../api/client";
import { anchoredPosition } from "../utils/anchorPosition";
import { useConfirm } from "./ConfirmProvider";
import { IconBookmark } from "./SheetIcons";

/** Two states that show the same rows compare equal, whatever order their keys came in. */
export function viewStateKey(s: ViewState): string {
  return JSON.stringify([
    s.source,
    s.search ?? "",
    [...s.search_columns].sort(),
    s.filters.map((f) => [f.column, f.op, f.value ?? null, f.values ?? null]),
    s.sort_by ?? null,
    s.sort_by ? s.sort_dir : "asc",
    s.group_by,
    s.only_recent,
  ]);
}

/** The link that opens a view. Works for anyone only once the view is shared. */
export function viewLink(datasetId: string, viewId: string): string {
  return `${window.location.origin}/datasets/${datasetId}/explore?view=${viewId}`;
}

interface Props {
  datasetId: string;
  /** what the table is showing right now */
  current: ViewState;
  /** the view last opened, if the table was opened from one */
  activeView: SavedView | null;
  /** whether the table has moved away from the active view since it was opened */
  modified: boolean;
  onApply: (view: SavedView) => void;
  /** the active view was deleted, or changed in a way the page should know about */
  onActiveChanged: (view: SavedView | null) => void;
}

/**
 * Saved views.
 *
 * A view is a question asked of the file - a search, its filters, a sort - kept under a
 * name so it can be asked again in one click. It does not carry the columns: those are
 * the arrangement, which each reader keeps in their own browser.
 * Mixing the two would mean opening "Toyota since 2020" also rearranged the table, which
 * nobody asking that question meant.
 */
export default function SavedViewsMenu(props: Props) {
  const { datasetId, current, activeView, modified } = props;
  const { t } = useTranslation();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ left: 0, top: 0, maxHeight: 480 });
  const [name, setName] = useState("");
  const [share, setShare] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const { data: views } = useQuery({
    queryKey: ["views", datasetId],
    queryFn: () => listSavedViews(datasetId),
    staleTime: 30 * 1000,
  });

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const target = e.target as Node;
      if (popoverRef.current?.contains(target) || buttonRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function refresh() {
    qc.invalidateQueries({ queryKey: ["views", datasetId] });
  }

  function failed(err: unknown) {
    setNotice(null);
    setError(apiErrorMessage(err, t("common.error_generic")));
  }

  const createMutation = useMutation({
    mutationFn: () =>
      createSavedView(datasetId, { name: name.trim(), state: current, shared: share }),
    onSuccess: (view) => {
      setName("");
      setShare(false);
      setError(null);
      setNotice(t("views.saved", { name: view.name }));
      refresh();
      props.onActiveChanged(view);
    },
    onError: failed,
  });

  const updateMutation = useMutation({
    mutationFn: ({ view, body }: { view: SavedView; body: { state?: ViewState; shared?: boolean } }) =>
      updateSavedView(datasetId, view.id, body),
    onSuccess: (view) => {
      setError(null);
      refresh();
      if (activeView?.id === view.id) props.onActiveChanged(view);
    },
    onError: failed,
  });

  const deleteMutation = useMutation({
    mutationFn: (view: SavedView) => deleteSavedView(datasetId, view.id),
    onSuccess: (_r, view) => {
      setError(null);
      setNotice(null);
      refresh();
      if (activeView?.id === view.id) props.onActiveChanged(null);
    },
    onError: failed,
  });

  async function copyLink(view: SavedView) {
    try {
      await navigator.clipboard.writeText(viewLink(datasetId, view.id));
      setError(null);
      setNotice(t("views.link_copied", { name: view.name }));
    } catch {
      setNotice(viewLink(datasetId, view.id));
    }
  }

  async function remove(view: SavedView) {
    const body = view.shared
      ? t("views.confirm_delete_shared", { name: view.name })
      : t("views.confirm_delete", { name: view.name });
    if (await confirm({ body })) deleteMutation.mutate(view);
  }

  const mine = (views ?? []).filter((v) => v.mine);
  const others = (views ?? []).filter((v) => !v.mine);
  const busy = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

  function renderView(view: SavedView) {
    const isActive = activeView?.id === view.id;
    return (
      <li key={view.id} className={`saved-view${isActive ? " is-active" : ""}`}>
        <button
          type="button"
          className="saved-view-open"
          onClick={() => {
            props.onApply(view);
            setOpen(false);
          }}
        >
          <span className="saved-view-name" dir="auto">{view.name}</span>
          {isActive && modified && <span className="saved-view-tag">{t("views.modified")}</span>}
          {view.shared && view.mine && <span className="saved-view-tag shared">{t("views.shared_tag")}</span>}
          {!view.mine && (
            <span className="saved-view-owner" dir="auto">
              {t("views.by", { name: view.owner_username })}
            </span>
          )}
        </button>
        <div className="saved-view-actions">
          {view.mine && isActive && modified && (
            <button
              type="button"
              className="link-btn"
              disabled={busy}
              onClick={() => updateMutation.mutate({ view, body: { state: current } })}
            >
              {t("views.update")}
            </button>
          )}
          {view.mine && (
            <button
              type="button"
              className="link-btn"
              disabled={busy}
              onClick={() => updateMutation.mutate({ view, body: { shared: !view.shared } })}
            >
              {view.shared ? t("views.unshare") : t("views.share")}
            </button>
          )}
          {view.shared && (
            <button type="button" className="link-btn" onClick={() => copyLink(view)}>
              {t("views.copy_link")}
            </button>
          )}
          {view.can_delete && (
            <button type="button" className="link-btn danger" disabled={busy} onClick={() => remove(view)}>
              {t("views.delete")}
            </button>
          )}
        </div>
      </li>
    );
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className={`sheet-tool${activeView ? " active" : ""}`}
        onClick={() => {
          if (buttonRef.current) {
            setPos(
              anchoredPosition(buttonRef.current.getBoundingClientRect(), {
                width: 340,
                preferredHeight: 520,
              })
            );
          }
          setError(null);
          setNotice(null);
          setOpen((o) => !o);
        }}
        aria-expanded={open}
        title={activeView ? activeView.name : undefined}
      >
        <IconBookmark />
        <span className="saved-views-label" dir="auto">
          {activeView ? activeView.name : t("views.button")}
        </span>
        {activeView && modified && <span className="saved-views-dot" aria-label={t("views.modified")} />}
      </button>

      {open && (
        <div
          ref={popoverRef}
          className="saved-views-popover"
          style={{ position: "fixed", left: pos.left, top: pos.top, maxHeight: pos.maxHeight }}
          role="dialog"
          aria-label={t("views.title")}
        >
          <form
            className="saved-views-save"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) createMutation.mutate();
            }}
          >
            <label className="saved-views-heading" htmlFor="saved-view-name">
              {t("views.save_current")}
            </label>
            <p className="saved-views-note">{t("views.save_hint")}</p>
            <div className="saved-views-row">
              <input
                id="saved-view-name"
                type="text"
                dir="auto"
                maxLength={80}
                value={name}
                placeholder={t("views.name_placeholder") ?? ""}
                onChange={(e) => setName(e.target.value)}
              />
              <button type="submit" className="btn" disabled={!name.trim() || busy}>
                {t("views.save")}
              </button>
            </div>
            <label className="saved-views-check">
              <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} />
              <span>{t("views.share_label")}</span>
            </label>
          </form>

          {error && <p className="saved-views-error" role="alert">{error}</p>}
          {notice && <p className="saved-views-notice" role="status">{notice}</p>}

          <section>
            <h3 className="saved-views-heading">{t("views.mine")}</h3>
            {mine.length === 0 ? (
              <p className="saved-views-note">{t("views.empty")}</p>
            ) : (
              <ul className="saved-views-list">{mine.map(renderView)}</ul>
            )}
          </section>

          {others.length > 0 && (
            <section>
              <h3 className="saved-views-heading">{t("views.others")}</h3>
              <ul className="saved-views-list">{others.map(renderView)}</ul>
            </section>
          )}
        </div>
      )}
    </>
  );
}
