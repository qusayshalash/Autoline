import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useConfirm } from "../../components/ConfirmProvider";

import {
  createRole,
  deleteRole,
  fetchPermissions,
  fetchRole,
  fetchRoles,
  updateRole,
} from "../../api/admin";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { IconKey, IconPlus, IconShield, IconTrash, IconUsers } from "../../components/admin/AdminIcons";
import { AdminPanel, Drawer } from "../../components/admin/AdminUI";
import { formatDateTime } from "../../data/datetime";
import ErrorBanner from "../../components/ErrorBanner";
import LoadingState from "../../components/LoadingState";

const ACTION_ORDER = ["view", "create", "update", "delete", "export", "manage"];

export default function RolesPage() {
  const { t, i18n } = useTranslation();
  const confirm = useConfirm();
  const { can } = useAuth();
  const qc = useQueryClient();

  const [openSlug, setOpenSlug] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: roles, isLoading } = useQuery({ queryKey: ["admin-roles"], queryFn: fetchRoles });
  const { data: permissions } = useQuery({ queryKey: ["admin-permissions"], queryFn: fetchPermissions });
  const totalPermissions = permissions?.length ?? 0;

  function invalidate() {
    qc.invalidateQueries({ queryKey: ["admin-roles"] });
    qc.invalidateQueries({ queryKey: ["admin-role"] });
    qc.invalidateQueries({ queryKey: ["admin-overview"] });
    qc.invalidateQueries({ queryKey: ["admin-activity"] });
  }

  const remove = useMutation({
    mutationFn: (slug: string) => deleteRole(slug),
    onSuccess: () => {
      setError(null);
      setOpenSlug(null);
      invalidate();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  if (isLoading) return <LoadingState />;

  return (
    <div className="admin-page">
      <AdminPanel
        icon={<IconShield />}
        title={t("admin.roles.title", { count: roles?.length ?? 0 })}
        actions={
          can("roles.manage") && (
            <button className="btn" onClick={() => setCreateOpen(true)}>
              <IconPlus />
              {t("admin.roles.add")}
            </button>
          )
        }
      >
        <ErrorBanner message={error} />
        <div className="role-grid">
          {(roles ?? []).map((r) => (
            <button className="role-card" key={r.slug} onClick={() => setOpenSlug(r.slug)}>
              <span className="role-card-head">
                <span className="role-mark" aria-hidden="true">
                  <IconShield />
                </span>
                {/* dir="auto" on everything a person typed or the database holds: a role
                    named or described in English inside an Arabic page has its trailing
                    period moved to the front by the bidirectional algorithm, which is
                    how ".Full access to the system" came to be on screen. */}
                <strong dir="auto">{r.name}</strong>
                {r.is_system && <span className="role-badge">{t("admin.roles.system")}</span>}
              </span>
              <span className="role-desc" dir="auto">
                {r.description || "—"}
              </span>
              {/* The number goes through the translation rather than sitting beside it:
                  Arabic agreement depends on the count, so "2 مستخدم" has to become
                  "مستخدمان" and "4 صلاحية" has to become "صلاحيات". A number rendered
                  outside the string cannot reach the rule that decides its noun. */}
              <span className="role-stats">
                <span className="role-stat">
                  <IconUsers />
                  {t("admin.roles.users", { count: r.user_count })}
                </span>
                <span className="role-stat">
                  <IconKey />
                  {t("admin.roles.permissions", { count: r.permission_count })}
                </span>
              </span>
              {/* How much of the system this role reaches. The count alone says little -
                  4 permissions is most of the app or almost none of it depending on how
                  many there are - and it is the first thing anybody wants to know about
                  a role they did not create. */}
              <span
                className="role-reach"
                role="img"
                aria-label={t("admin.roles.reach", {
                  granted: r.permission_count,
                  total: totalPermissions,
                })}
              >
                <span
                  style={{
                    inlineSize: totalPermissions
                      ? `${Math.round((r.permission_count / totalPermissions) * 100)}%`
                      : "0%",
                  }}
                />
              </span>
              <span className="role-updated">
                {t("admin.roles.updated")}: {formatDateTime(r.updated_at, i18n.language)}
              </span>
            </button>
          ))}
        </div>
      </AdminPanel>

      {openSlug && (
        <RoleDrawer
          slug={openSlug}
          permissions={permissions ?? []}
          onClose={() => setOpenSlug(null)}
          onSaved={invalidate}
          onDelete={async (slug) => {
            if (await confirm({ body: t("admin.roles.confirm_delete") })) remove.mutate(slug);
          }}
        />
      )}

      <CreateRoleDrawer
        open={createOpen}
        permissions={permissions ?? []}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false);
          invalidate();
        }}
      />
    </div>
  );
}

/** Groups the flat permission list into a module × action grid. */
function useMatrix(permissions: { key: string; module: string; action: string }[]) {
  return useMemo(() => {
    const modules = [...new Set(permissions.map((p) => p.module))];
    const actions = ACTION_ORDER.filter((a) => permissions.some((p) => p.action === a));
    const lookup = new Map(permissions.map((p) => [`${p.module}:${p.action}`, p.key]));
    return { modules, actions, lookup };
  }, [permissions]);
}

function PermissionMatrix({
  permissions,
  selected,
  disabled,
  onToggle,
  onToggleModule,
}: {
  permissions: { key: string; module: string; action: string }[];
  selected: Set<string>;
  disabled: boolean;
  onToggle: (key: string) => void;
  onToggleModule: (keys: string[], on: boolean) => void;
}) {
  const { t } = useTranslation();
  const { modules, actions, lookup } = useMatrix(permissions);

  return (
    <div className="matrix-wrap">
      <table className="perm-matrix">
        <thead>
          <tr>
            <th>{t("admin.roles.module")}</th>
            {actions.map((a) => (
              <th key={a}>{t(`admin.permission_actions.${a}`, { defaultValue: a })}</th>
            ))}
            <th className="matrix-all">{t("admin.roles.all")}</th>
          </tr>
        </thead>
        <tbody>
          {modules.map((m) => {
            const keys = permissions.filter((p) => p.module === m).map((p) => p.key);
            const allOn = keys.every((k) => selected.has(k));
            // A checkbox in a grid has nothing beside it to read: its row and column
            // headings name it on screen, but a screen reader announces only the name
            // it carries. Built from the same two translations the headings use.
            const moduleName = t(`admin.modules.${m}`, { defaultValue: m });
            const granted = keys.filter((k) => selected.has(k)).length;
            return (
              <tr key={m} className={granted === 0 ? "is-empty" : undefined}>
                <th scope="row">
                  <span className="matrix-module">
                    {t(`admin.modules.${m}`, { defaultValue: m })}
                    <span className="matrix-count">
                      {granted}/{keys.length}
                    </span>
                  </span>
                </th>
                {actions.map((a) => {
                  const key = lookup.get(`${m}:${a}`);
                  return (
                    <td key={a}>
                      {key ? (
                        <input
                          type="checkbox"
                          checked={selected.has(key)}
                          disabled={disabled}
                          onChange={() => onToggle(key)}
                          aria-label={t("admin.roles.toggle_permission", {
                            module: moduleName,
                            action: t(`admin.permission_actions.${a}`, { defaultValue: a }),
                          })}
                        />
                      ) : (
                        <span className="matrix-na" title={t("admin.roles.not_applicable") ?? ""}>
                          <span aria-hidden="true" />
                          <span className="sr-only">{t("admin.roles.not_applicable")}</span>
                        </span>
                      )}
                    </td>
                  );
                })}
                <td className="matrix-all">
                  <input
                    type="checkbox"
                    checked={allOn}
                    disabled={disabled}
                    onChange={() => onToggleModule(keys, !allOn)}
                    aria-label={t("admin.roles.toggle_module", { module: moduleName })}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RoleDrawer({
  slug,
  permissions,
  onClose,
  onSaved,
  onDelete,
}: {
  slug: string;
  permissions: { key: string; module: string; action: string }[];
  onClose: () => void;
  onSaved: () => void;
  onDelete: (slug: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const { can } = useAuth();
  const { data: role } = useQuery({ queryKey: ["admin-role", slug], queryFn: () => fetchRole(slug) });

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (role) {
      setSelected(new Set(role.permissions));
      setDescription(role.description);
    }
  }, [role]);

  const save = useMutation({
    mutationFn: () => updateRole(slug, { description, permissions: [...selected] }),
    onSuccess: () => {
      setError(null);
      onSaved();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  // Super Admin is intentionally immutable: it is the account of last resort.
  const locked = !can("roles.manage") || slug === "super_admin";
  const dirty =
    !!role &&
    (description !== role.description ||
      selected.size !== role.permissions.length ||
      role.permissions.some((p) => !selected.has(p)));

  return (
    <Drawer
      open
      title={role?.name ?? slug}
      onClose={onClose}
      footer={
        <>
          {can("roles.manage") && role && !role.is_system && (
            <button className="btn danger" onClick={() => onDelete(slug)}>
              <IconTrash />
              {t("admin.roles.delete")}
            </button>
          )}
          <span style={{ flex: 1 }} />
          {!locked && (
            <button className="btn" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
              {t("admin.roles.save")}
            </button>
          )}
        </>
      }
    >
      {!role ? (
        <LoadingState />
      ) : (
        <>
          <dl className="detail-list">
            <div>
              <dt>{t("admin.roles.slug")}</dt>
              <dd className="mono">{role.slug}</dd>
            </div>
            <div>
              <dt>{t("admin.roles.users_label")}</dt>
              <dd>{role.user_count}</dd>
            </div>
            <div>
              <dt>{t("admin.roles.updated")}</dt>
              <dd>{formatDateTime(role.updated_at, i18n.language)}</dd>
            </div>
          </dl>

          <label className="stacked-field">
            {t("admin.roles.description")}
            <textarea
              rows={2}
              dir="auto"
              value={description}
              disabled={locked}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>

          {slug === "super_admin" && <p className="muted admin-note">{t("admin.roles.super_admin_note")}</p>}

          <h3 className="drawer-section">
            {t("admin.roles.matrix")} <span className="muted">({selected.size})</span>
          </h3>
          <PermissionMatrix
            permissions={permissions}
            selected={selected}
            disabled={locked}
            onToggle={(key) =>
              setSelected((prev) => {
                const next = new Set(prev);
                if (next.has(key)) next.delete(key);
                else next.add(key);
                return next;
              })
            }
            onToggleModule={(keys, on) =>
              setSelected((prev) => {
                const next = new Set(prev);
                keys.forEach((k) => (on ? next.add(k) : next.delete(k)));
                return next;
              })
            }
          />
          <ErrorBanner message={error} />
        </>
      )}
    </Drawer>
  );
}

function CreateRoleDrawer({
  open,
  permissions,
  onClose,
  onCreated,
}: {
  open: boolean;
  permissions: { key: string; module: string; action: string }[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => createRole({ name, description, permissions: [...selected] }),
    onSuccess: () => {
      setName("");
      setDescription("");
      setSelected(new Set());
      setError(null);
      onCreated();
    },
    onError: (e) => setError(apiErrorMessage(e, t("common.error_generic"))),
  });

  return (
    <Drawer
      open={open}
      title={t("admin.roles.add")}
      onClose={onClose}
      footer={
        <button className="btn" disabled={name.trim().length < 2 || create.isPending} onClick={() => create.mutate()}>
          {t("admin.roles.create")}
        </button>
      }
    >
      <div className="form-grid">
        <label>
          {t("admin.roles.name")} *
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          {t("admin.roles.description")}
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
      </div>

      <h3 className="drawer-section">
        {t("admin.roles.matrix")} <span className="muted">({selected.size})</span>
      </h3>
      <PermissionMatrix
        permissions={permissions}
        selected={selected}
        disabled={false}
        onToggle={(key) =>
          setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
          })
        }
        onToggleModule={(keys, on) =>
          setSelected((prev) => {
            const next = new Set(prev);
            keys.forEach((k) => (on ? next.add(k) : next.delete(k)));
            return next;
          })
        }
      />
      <ErrorBanner message={error} />
    </Drawer>
  );
}
