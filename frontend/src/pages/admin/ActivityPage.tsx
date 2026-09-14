import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchActivity, fetchUsers } from "../../api/admin";
import i18n from "../../i18n";
import { IconActivity } from "../../components/admin/AdminIcons";
import { AdminPanel } from "../../components/admin/AdminUI";
import QueryState from "../../components/QueryState";
import ActivityRow from "./ActivityRow";

const PAGE_SIZE = 50;

/**
 * Every action the filter can offer, taken from the labels rather than listed again.
 *
 * It used to be a second hand-written list, and it drifted: fourteen entries against the
 * twenty-seven the server records, so a backup, a trim or a rename could not be filtered
 * for at all. The labels are the better source because they are already held to the
 * server's list by a test - see backend/tests/test_activity_translations.py - so an
 * action that exists has a name here, and one with a name can be filtered.
 */
function knownActions(): string[] {
  const candidates = [i18n.language, i18n.options.fallbackLng, "ar"].flat();
  for (const language of candidates) {
    if (!language) continue;
    const bundle = i18n.getResourceBundle(String(language), "translation");
    const actions = bundle?.admin?.actions;
    if (actions) return Object.keys(actions);
  }
  return [];
}

export default function ActivityPage() {
  const { t, i18n: active } = useTranslation();
  // sorted by what the reader sees, not by the key behind it
  const actions = useMemo(
    () =>
      knownActions().sort((a, b) =>
        t(`admin.actions.${a}`, { defaultValue: a }).localeCompare(
          t(`admin.actions.${b}`, { defaultValue: b }),
          active.language
        )
      ),
    [t, active.language]
  );
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [page, setPage] = useState(0);

  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: fetchUsers });
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin-activity", "page", action, actor, page],
    queryFn: () =>
      fetchActivity({ limit: PAGE_SIZE, offset: page * PAGE_SIZE, action: action || null, actor_id: actor || null }),
  });

  const totalPages = useMemo(() => Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE)), [data]);

  return (
    <div className="admin-page">
      <AdminPanel
        icon={<IconActivity />}
        title={t("admin.activity.title", { count: data?.total ?? 0 })}
        actions={
          <div className="admin-toolbar tight">
            <select
              value={action}
              aria-label={t("admin.activity.filter_by_action") ?? ""}
              onChange={(e) => {
                setAction(e.target.value);
                setPage(0);
              }}
            >
              <option value="">{t("admin.activity.all_actions")}</option>
              {actions.map((a) => (
                <option key={a} value={a}>
                  {t(`admin.actions.${a}`, { defaultValue: a })}
                </option>
              ))}
            </select>
            <select
              value={actor}
              aria-label={t("admin.activity.filter_by_actor") ?? ""}
              onChange={(e) => {
                setActor(e.target.value);
                setPage(0);
              }}
            >
              <option value="">{t("admin.activity.all_actors")}</option>
              {(users ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name || u.username}
                </option>
              ))}
            </select>
          </div>
        }
      >
        {isLoading || isError ? (
          <QueryState loading={isLoading} error={isError ? error : null} onRetry={refetch} />
        ) : data && data.items.length > 0 ? (
          <>
            <ul className="activity-list">
              {data.items.map((item) => (
                <ActivityRow key={item.id} item={item} />
              ))}
            </ul>
            {totalPages > 1 && (
              <div className="admin-pager">
                <button className="btn secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  {t("explorer.prev")}
                </button>
                <span className="muted">
                  {page + 1} / {totalPages}
                </span>
                <button
                  className="btn secondary"
                  disabled={page + 1 >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  {t("explorer.next")}
                </button>
              </div>
            )}
          </>
        ) : (
          <p className="muted">{t("admin.overview.no_activity")}</p>
        )}
      </AdminPanel>
    </div>
  );
}
