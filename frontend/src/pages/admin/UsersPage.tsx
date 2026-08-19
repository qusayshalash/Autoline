import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  createUser,
  deleteUser,
  fetchActivity,
  fetchRoles,
  fetchUsers,
  updateUser,
  type AdminUser,
  type UserStatus,
} from "../../api/admin";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconPlus, IconSearch, IconTrash, IconUsers } from "../../components/admin/AdminIcons";
import {
  AdminPanel,
  Drawer,
  StatusPill,
  formatDateTime,
  formatRelative,
} from "../../components/admin/AdminUI";
import ErrorBanner from "../../components/ErrorBanner";
import LoadingState from "../../components/LoadingState";
import ActivityRow from "./ActivityRow";

const STATUSES: UserStatus[] = ["active", "inactive", "suspended", "pending"];

export default function AdminUsersPage() {
  const { t } = useTranslation();
  const { user: me, can } = useAuth();
  const qc = useQueryClient();

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detailId, setDetailId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: users, isLoading } = useQuery({ queryKey: ["admin-users"], queryFn: fetchUsers });
  const { data: roles } = useQuery({ queryKey: ["admin-roles"], queryFn: fetchRoles });

  function invalidate() {
    qc.invalidateQueries({ queryKey: ["admin-users"] });
    qc.invalidateQueries({ queryKey: ["admin-overview"] });
    qc.invalidateQueries({ queryKey: ["admin-activity"] });
    qc.invalidateQueries({ queryKey: ["admin-roles"] });
  }

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateUser>[1] }) =>
      updateUser(id, body),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteUser(id),
    onSuccess: () => {
      setError(null);
      setDetailId(null);
      setSelected(new Set());
      invalidate();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (users ?? []).filter((u) => {
      if (roleFilter && u.role !== roleFilter) return false;
      if (statusFilter && u.status !== statusFilter) return false;
      if (!q) return true;
      return [u.username, u.full_name, u.email].some((v) => (v || "").toLowerCase().includes(q));
    });
  }, [users, search, roleFilter, statusFilter]);

  const detail = (users ?? []).find((u) => u.id === detailId) ?? null;
  const allSelected = filtered.length > 0 && filtered.every((u) => selected.has(u.id));

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(filtered.map((u) => u.id)));
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  /** Bulk actions run sequentially so a rejection (e.g. the last user manager) surfaces
   *  as a real error instead of being lost among parallel requests. */
  async function bulk(action: "activate" | "suspend" | "delete") {
    setError(null);
    for (const id of selected) {
      try {
        if (action === "delete") await deleteUser(id);
        else await updateUser(id, { status: action === "activate" ? "active" : "suspended" });
      } catch (e) {
        setError(apiErrorMessage(e, t("common.error_generic")));
        break;
      }
    }
    setSelected(new Set());
    invalidate();
  }

  if (isLoading) return <LoadingState />;

  return (
    <div className="admin-page">
      <AdminPanel
        icon={<IconUsers />}
        title={t("admin.users.title", { count: filtered.length })}
        actions={
          can("users.create") && (
            <button className="btn" onClick={() => setCreateOpen(true)}>
              <IconPlus />
              {t("admin.users.add")}
            </button>
          )
        }
      >
        <div className="admin-toolbar">
          <span className="admin-search">
            <IconSearch />
            <input
              type="search"
              value={search}
              placeholder={t("admin.users.search") ?? ""}
              onChange={(e) => setSearch(e.target.value)}
            />
          </span>
          <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <option value="">{t("admin.users.all_roles")}</option>
            {(roles ?? []).map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.name}
              </option>
            ))}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">{t("admin.users.all_statuses")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`admin.status.${s}`)}
              </option>
            ))}
          </select>
        </div>

        {selected.size > 0 && (
          <div className="bulk-bar">
            <span>{t("admin.users.selected", { count: selected.size })}</span>
            {can("users.update") && (
              <>
                <button className="btn secondary" onClick={() => bulk("activate")}>
                  {t("admin.users.activate")}
                </button>
                <button className="btn secondary" onClick={() => bulk("suspend")}>
                  {t("admin.users.suspend")}
                </button>
              </>
            )}
            {can("users.delete") && (
              <button
                className="btn danger"
                onClick={() => {
                  if (window.confirm(t("admin.users.confirm_bulk_delete", { count: selected.size }) ?? ""))
                    bulk("delete");
                }}
              >
                {t("admin.users.delete")}
              </button>
            )}
            <button className="link-btn" onClick={() => setSelected(new Set())}>
              {t("admin.users.clear_selection")}
            </button>
          </div>
        )}

        <ErrorBanner message={error} />

        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="tick">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="select all" />
                </th>
                <th>{t("admin.users.name")}</th>
                <th>{t("admin.users.email")}</th>
                <th>{t("admin.users.username")}</th>
                <th>{t("admin.users.role")}</th>
                <th>{t("admin.users.status")}</th>
                <th>{t("admin.users.last_login")}</th>
                <th>{t("admin.users.created")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id} className={detailId === u.id ? "is-open" : undefined}>
                  <td className="tick">
                    <input
                      type="checkbox"
                      checked={selected.has(u.id)}
                      onChange={() => toggleOne(u.id)}
                      aria-label={u.username}
                    />
                  </td>
                  <td>
                    <button className="cell-link" onClick={() => setDetailId(u.id)}>
                      {u.full_name || "—"}
                    </button>
                  </td>
                  <td>{u.email || "—"}</td>
                  <td className="mono">{u.username}</td>
                  <td>{roles?.find((r) => r.slug === u.role)?.name ?? u.role}</td>
                  <td>
                    <StatusPill status={u.status} />
                  </td>
                  <td>{u.last_login_at ? formatRelative(u.last_login_at, t) : "—"}</td>
                  <td>{formatDateTime(u.created_at)}</td>
                  <td className="row-actions">
                    <button className="link-btn" onClick={() => setDetailId(u.id)}>
                      {t("admin.users.view")}
                    </button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="muted empty-row">
                    {t("admin.users.none")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </AdminPanel>

      <UserDrawer
        user={detail}
        roles={roles ?? []}
        isSelf={detail?.id === me?.id}
        onClose={() => setDetailId(null)}
        onPatch={(body) => detail && patch.mutate({ id: detail.id, body })}
        onDelete={() => {
          if (detail && window.confirm(t("admin.users.confirm_delete", { name: detail.username }) ?? ""))
            remove.mutate(detail.id);
        }}
      />

      <CreateUserDrawer
        open={createOpen}
        roles={roles ?? []}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false);
          invalidate();
        }}
      />
    </div>
  );
}

function UserDrawer({
  user,
  roles,
  isSelf,
  onClose,
  onPatch,
  onDelete,
}: {
  user: AdminUser | null;
  roles: { slug: string; name: string }[];
  isSelf: boolean;
  onClose: () => void;
  onPatch: (body: Parameters<typeof updateUser>[1]) => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const [newPassword, setNewPassword] = useState("");

  const { data: activity } = useQuery({
    queryKey: ["admin-activity", "user", user?.id],
    queryFn: () => fetchActivity({ limit: 8, actor_id: user!.id }),
    enabled: !!user,
  });

  const { data: roleDetail } = useQuery({
    queryKey: ["admin-role", user?.role],
    queryFn: async () => (await import("../../api/admin")).fetchRole(user!.role),
    enabled: !!user,
  });

  if (!user) return null;

  return (
    <Drawer
      open
      title={user.full_name || user.username}
      onClose={onClose}
      footer={
        can("users.delete") && !isSelf ? (
          <button className="btn danger" onClick={onDelete}>
            <IconTrash />
            {t("admin.users.delete")}
          </button>
        ) : null
      }
    >
      <dl className="detail-list">
        <div>
          <dt>{t("admin.users.username")}</dt>
          <dd className="mono">{user.username}</dd>
        </div>
        <div>
          <dt>{t("admin.users.email")}</dt>
          <dd>{user.email || "—"}</dd>
        </div>
        <div>
          <dt>{t("admin.users.status")}</dt>
          <dd>
            {can("users.update") ? (
              <select value={user.status} onChange={(e) => onPatch({ status: e.target.value as UserStatus })}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {t(`admin.status.${s}`)}
                  </option>
                ))}
              </select>
            ) : (
              <StatusPill status={user.status} />
            )}
          </dd>
        </div>
        <div>
          <dt>{t("admin.users.role")}</dt>
          <dd>
            {can("users.update") ? (
              <select value={user.role} onChange={(e) => onPatch({ role: e.target.value })}>
                {roles.map((r) => (
                  <option key={r.slug} value={r.slug}>
                    {r.name}
                  </option>
                ))}
              </select>
            ) : (
              user.role
            )}
          </dd>
        </div>
        <div>
          <dt>{t("admin.users.last_login")}</dt>
          <dd>{formatDateTime(user.last_login_at)}</dd>
        </div>
        <div>
          <dt>{t("admin.users.created")}</dt>
          <dd>{formatDateTime(user.created_at)}</dd>
        </div>
      </dl>

      <h3 className="drawer-section">{t("admin.users.permissions")}</h3>
      {roleDetail ? (
        <div className="perm-chips">
          {roleDetail.permissions.length === 0 && <span className="muted">—</span>}
          {roleDetail.permissions.map((p) => (
            <span className="perm-chip" key={p}>
              {p}
            </span>
          ))}
        </div>
      ) : (
        <p className="muted">…</p>
      )}

      {can("users.update") && (
        <>
          <h3 className="drawer-section">{t("admin.users.reset_password")}</h3>
          <div className="inline-form">
            <input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              placeholder={t("users.new_password") ?? ""}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            <button
              className="btn secondary"
              disabled={newPassword.length < 6}
              onClick={() => {
                onPatch({ password: newPassword });
                setNewPassword("");
              }}
            >
              {t("users.change_password")}
            </button>
          </div>
        </>
      )}

      <h3 className="drawer-section">{t("admin.users.recent_activity")}</h3>
      {activity && activity.items.length > 0 ? (
        <ul className="activity-list">
          {activity.items.map((a) => (
            <ActivityRow key={a.id} item={a} />
          ))}
        </ul>
      ) : (
        <p className="muted">{t("admin.overview.no_activity")}</p>
      )}
    </Drawer>
  );
}

function CreateUserDrawer({
  open,
  roles,
  onClose,
  onCreated,
}: {
  open: boolean;
  roles: { slug: string; name: string }[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    username: "",
    password: "",
    full_name: "",
    email: "",
    role: "viewer",
    status: "active" as UserStatus,
  });
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => createUser(form),
    onSuccess: () => {
      setForm({ username: "", password: "", full_name: "", email: "", role: "viewer", status: "active" });
      setError(null);
      onCreated();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  const valid = form.username.length >= 3 && form.password.length >= 6 && form.role;

  return (
    <Drawer
      open={open}
      title={t("admin.users.add")}
      onClose={onClose}
      footer={
        <button className="btn" disabled={!valid || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? t("users.creating") : t("users.create")}
        </button>
      }
    >
      <div className="form-grid">
        <label>
          {t("admin.users.name")}
          <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </label>
        <label>
          {t("admin.users.email")}
          <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </label>
        <label>
          {t("admin.users.username")} *
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </label>
        <label>
          {t("auth.password")} *
          <input
            type="password"
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </label>
        <label>
          {t("admin.users.role")}
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {roles.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("admin.users.status")}
          <select
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value as UserStatus })}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`admin.status.${s}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ErrorBanner message={error} />
    </Drawer>
  );
}
