import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchActivity, fetchUsers } from "../../api/admin";
import { IconActivity } from "../../components/admin/AdminIcons";
import { AdminPanel } from "../../components/admin/AdminUI";
import LoadingState from "../../components/LoadingState";
import ActivityRow from "./ActivityRow";

const PAGE_SIZE = 50;

/** Action values the log can hold, grouped for the filter. Kept in one place so the
 *  filter never offers something the backend cannot produce. */
const ACTIONS = [
  "auth.login",
  "user.created",
  "user.updated",
  "user.password_reset",
  "user.deleted",
  "role.created",
  "role.updated",
  "role.deleted",
  "dataset.imported",
  "dataset.cleaned",
  "dataset.deleted",
  "language.updated",
  "language.default_changed",
];

export default function ActivityPage() {
  const { t } = useTranslation();
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [page, setPage] = useState(0);

  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: fetchUsers });
  const { data, isLoading } = useQuery({
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
              onChange={(e) => {
                setAction(e.target.value);
                setPage(0);
              }}
            >
              <option value="">{t("admin.activity.all_actions")}</option>
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {t(`admin.actions.${a}`, { defaultValue: a })}
                </option>
              ))}
            </select>
            <select
              value={actor}
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
        {isLoading ? (
          <LoadingState />
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
