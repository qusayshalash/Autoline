import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { createUser, deleteUser, listUsers, updateUser, type Role, type User } from "../api/client";
import LoadingState from "../components/LoadingState";
import PasswordField from "../components/PasswordField";

const ROLES: Role[] = ["admin", "editor", "viewer"];

function errorMessage(err: unknown, fallback: string): string {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback;
}

function UserRow({
  user,
  onUpdate,
  onDelete,
}: {
  user: User;
  onUpdate: (body: Parameters<typeof updateUser>[1]) => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const [newPassword, setNewPassword] = useState("");
  const [savedMessage, setSavedMessage] = useState(false);

  const changePasswordMutation = useMutation({
    mutationFn: () => updateUser(user.id, { password: newPassword }),
    onSuccess: () => {
      setNewPassword("");
      setSavedMessage(true);
      setTimeout(() => setSavedMessage(false), 2000);
    },
    onError: (err: unknown) => window.alert(errorMessage(err, t("users.cannot_remove_last_admin"))),
  });

  return (
    <tr>
      <td>{user.username}</td>
      <td>
        <select value={user.role} onChange={(e) => onUpdate({ role: e.target.value as Role })}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`auth.role_${r}`)}
            </option>
          ))}
        </select>
      </td>
      <td>
        <span className={`badge ${user.is_active ? "ready" : "error"}`}>
          {user.is_active ? t("users.active") : t("users.inactive")}
        </span>
      </td>
      <td>
        <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
          <PasswordField value={newPassword} onChange={setNewPassword} placeholder={t("users.new_password") ?? ""} />
          <button
            className="btn secondary"
            disabled={!newPassword || changePasswordMutation.isPending}
            onClick={() => changePasswordMutation.mutate()}
          >
            {changePasswordMutation.isPending ? t("users.changing_password") : t("users.change_password")}
          </button>
          {savedMessage && <span style={{ color: "var(--success)", fontSize: "0.8rem" }}>{t("users.password_changed")}</span>}
        </div>
      </td>
      <td style={{ display: "flex", gap: "0.4rem" }}>
        <button className="btn secondary" onClick={() => onUpdate({ is_active: !user.is_active })}>
          {user.is_active ? t("users.deactivate") : t("users.activate")}
        </button>
        <button
          className="btn danger"
          onClick={() => {
            if (window.confirm(t("users.confirm_delete") ?? "")) onDelete();
          }}
        >
          {t("users.delete")}
        </button>
      </td>
    </tr>
  );
}

export default function UsersPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const { data: users, isLoading } = useQuery({ queryKey: ["users"], queryFn: listUsers });

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [formError, setFormError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => createUser({ username, password, role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setUsername("");
      setPassword("");
      setRole("viewer");
      setFormError(null);
    },
    onError: (err: unknown) => setFormError(errorMessage(err, "Error")),
  });

  const updateMutation = useMutation({
    mutationFn: (vars: { id: string; body: Parameters<typeof updateUser>[1] }) => updateUser(vars.id, vars.body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (err: unknown) => window.alert(errorMessage(err, t("users.cannot_remove_last_admin"))),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (err: unknown) => window.alert(errorMessage(err, t("users.cannot_remove_last_admin"))),
  });

  return (
    <div>
      <h2>{t("users.title")}</h2>

      <div className="card">
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "flex-end" }}>
          <div className="field">
            <label>{t("users.username")}</label>
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div className="field">
            <label>{t("users.password")}</label>
            <PasswordField value={password} onChange={setPassword} />
          </div>
          <div className="field">
            <label>{t("users.role")}</label>
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`auth.role_${r}`)}
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn"
            disabled={!username || !password || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? t("users.creating") : t("users.create")}
          </button>
        </div>
        {formError && <p style={{ color: "var(--danger)" }}>{formError}</p>}
      </div>

      {isLoading ? (
        <LoadingState />
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t("users.username")}</th>
                <th>{t("users.role")}</th>
                <th>{t("users.status")}</th>
                <th>{t("users.change_password")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users?.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  onUpdate={(body) => updateMutation.mutate({ id: u.id, body })}
                  onDelete={() => deleteMutation.mutate(u.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
