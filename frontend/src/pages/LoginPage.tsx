import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import PasswordField from "../components/PasswordField";
import ThemeToggle from "../components/ThemeToggle";

export default function LoginPage() {
  const { t } = useTranslation();
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
      const from = (location.state as { from?: string })?.from ?? "/";
      navigate(from, { replace: true });
    } catch (err) {
      // 429 is the one refusal worth explaining. Every other failure stays deliberately
      // vague - saying which half of the pair was wrong tells an attacker which usernames
      // exist - but "you are locked out" is something the person in front of the screen
      // needs, otherwise a correct password appearing to fail looks like a broken system.
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 429) {
        setError(t("auth.too_many_attempts", { minutes: retryMinutes(err) }));
      } else {
        setError(t("auth.login_error"));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: "360px", margin: "3rem auto" }}>
      <div className="card">
        <h2>{t("auth.login_title")}</h2>
        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>{t("auth.username")}</label>
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </div>
          <div className="field">
            <label>{t("auth.password")}</label>
            <PasswordField value={password} onChange={setPassword} />
          </div>
          {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
          <button className="btn" type="submit" disabled={busy || !username || !password}>
            {busy ? t("common.loading") : t("auth.login_button")}
          </button>
        </form>
      </div>
      {/* the theme is reachable before signing in too - someone on a dark desktop
          should not have to log in through a white page first */}
      <div className="login-theme">
        <ThemeToggle />
      </div>
    </div>
  );
}

/** Retry-After is in seconds; a wait is easier to act on stated in minutes. */
function retryMinutes(err: unknown): number {
  const header = (err as { response?: { headers?: Record<string, string> } })?.response?.headers?.[
    "retry-after"
  ];
  const seconds = Number(header);
  return Number.isFinite(seconds) && seconds > 0 ? Math.max(1, Math.ceil(seconds / 60)) : 1;
}
