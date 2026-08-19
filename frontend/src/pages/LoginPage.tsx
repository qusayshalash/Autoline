import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import ThemeToggle from "../components/ThemeToggle";
import "./LoginPage.css";

const REMEMBERED_IDENTIFIER_KEY = "data-workspace-identifier";

const LOGIN_LANGUAGES = [
  { code: "ar", label: "العربية" },
  { code: "en", label: "English" },
  { code: "he", label: "עברית" },
] as const;

function getRememberedIdentifier(): string {
  try {
    return window.localStorage.getItem(REMEMBERED_IDENTIFIER_KEY) ?? "";
  } catch {
    return "";
  }
}

function persistRememberedIdentifier(identifier: string, shouldRemember: boolean) {
  try {
    if (shouldRemember) {
      window.localStorage.setItem(REMEMBERED_IDENTIFIER_KEY, identifier);
    } else {
      window.localStorage.removeItem(REMEMBERED_IDENTIFIER_KEY);
    }
  } catch {
    // The sign-in flow remains usable when browser storage is unavailable.
  }
}

export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState(getRememberedIdentifier);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberIdentifier, setRememberIdentifier] = useState(() => Boolean(getRememberedIdentifier()));
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);
  const activeLanguage = LOGIN_LANGUAGES.some(({ code }) => code === i18n.language.split("-")[0])
    ? i18n.language.split("-")[0]
    : "ar";
  const activeLanguageLabel = LOGIN_LANGUAGES.find(({ code }) => code === activeLanguage)?.label
    ?? LOGIN_LANGUAGES[0].label;

  if (user) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setAttemptedSubmit(true);
    setError(null);
    setNotice(null);

    const identifier = username.trim();
    if (!identifier || !password) {
      return;
    }

    setBusy(true);
    try {
      await login(identifier, password);
      persistRememberedIdentifier(identifier, rememberIdentifier);
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
    <main className="login-page">
      <div className="login-shell">
        <section className="login-panel" dir={i18n.dir()} aria-labelledby="login-heading">
          <div className="login-panel-inner">
            <div className="login-topbar" dir="ltr">
              <div className="login-brand" aria-label={t("app_title")}>
                <span className="login-brand-mark" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                  <span />
                </span>
                <span className="login-brand-copy" lang="en">
                  <strong>AutoLine</strong>
                  <small>Data Studio</small>
                </span>
              </div>
              <div className="login-topbar-controls">
                <label className="login-language-select">
                  <span className="login-globe-icon" aria-hidden="true" />
                  <span className="login-language-label" dir={i18n.dir()} aria-hidden="true">
                    {activeLanguageLabel}
                  </span>
                  <span className="login-select-chevron" aria-hidden="true" />
                  <select
                    className="login-language-native"
                    aria-label={t("common.language")}
                    value={activeLanguage}
                    onChange={(event) => void i18n.changeLanguage(event.currentTarget.value)}
                    dir={i18n.dir()}
                  >
                    {LOGIN_LANGUAGES.map(({ code, label }) => (
                      <option key={code} value={code}>{label}</option>
                    ))}
                  </select>
                </label>
                <ThemeToggle compact />
              </div>
            </div>

            <div className="login-form-wrap">
              <div className="login-auth-card">
                <div className="login-heading">
                  <span className="login-eyebrow">{t("auth.secure_access")}</span>
                  <h1 id="login-heading">{t("auth.welcome_back")}</h1>
                  <p>{t("auth.login_subtitle")}</p>
                </div>

                <form className="login-form" onSubmit={handleSubmit} noValidate>
                  <div className="login-field">
                    <label htmlFor="login-identifier">{t("auth.identifier")}</label>
                    <div className="login-text-control">
                      <span className="login-control-icon login-user-icon" aria-hidden="true" />
                      <input
                        id="login-identifier"
                        className="login-input"
                        type="text"
                        inputMode="email"
                        autoComplete="username"
                        placeholder={t("auth.identifier_placeholder")}
                        value={username}
                        onChange={(e) => {
                          setUsername(e.target.value);
                          setError(null);
                          setNotice(null);
                        }}
                        aria-invalid={attemptedSubmit && !username.trim()}
                        aria-describedby={attemptedSubmit && !username.trim() ? "login-identifier-error" : undefined}
                        autoFocus
                      />
                    </div>
                    {attemptedSubmit && !username.trim() && (
                      <p id="login-identifier-error" className="login-field-error">
                        {t("auth.identifier_required")}
                      </p>
                    )}
                  </div>

                  <div className="login-field">
                    <div className="login-field-label-row">
                      <label htmlFor="login-password">{t("auth.password")}</label>
                      <button
                        className="login-forgot-password"
                        type="button"
                        onClick={() => {
                          setNotice(t("auth.reset_hint"));
                          setError(null);
                        }}
                      >
                        {t("auth.forgot_password")}
                      </button>
                    </div>
                    <div className="login-text-control login-password-control">
                      <span className="login-control-icon login-lock-icon" aria-hidden="true" />
                      <input
                        id="login-password"
                        className="login-input"
                        type={showPassword ? "text" : "password"}
                        autoComplete="current-password"
                        placeholder={t("auth.password_placeholder")}
                        value={password}
                        onChange={(e) => {
                          setPassword(e.target.value);
                          setError(null);
                          setNotice(null);
                        }}
                        aria-invalid={attemptedSubmit && !password}
                        aria-describedby={attemptedSubmit && !password ? "login-password-error" : undefined}
                      />
                      <button
                        className={`login-password-toggle${showPassword ? " is-visible" : ""}`}
                        type="button"
                        onClick={() => setShowPassword((visible) => !visible)}
                        aria-label={showPassword ? t("common.hide_password") : t("common.show_password")}
                        aria-pressed={showPassword}
                        title={showPassword ? t("common.hide_password") : t("common.show_password")}
                      >
                        <span aria-hidden="true" />
                      </button>
                    </div>
                    {attemptedSubmit && !password && (
                      <p id="login-password-error" className="login-field-error">
                        {t("auth.password_required")}
                      </p>
                    )}
                  </div>

                  <label className="login-remember">
                    <input
                      type="checkbox"
                      checked={rememberIdentifier}
                      onChange={(e) => setRememberIdentifier(e.target.checked)}
                    />
                    <span>{t("auth.remember_identifier")}</span>
                  </label>

                  {error && (
                    <div className="login-alert login-alert-error" role="alert">
                      <span aria-hidden="true">!</span>
                      <p>{error}</p>
                    </div>
                  )}
                  {notice && (
                    <div className="login-alert login-alert-notice" role="status">
                      <span aria-hidden="true">i</span>
                      <p>{notice}</p>
                    </div>
                  )}

                  <button className="login-submit" type="submit" disabled={busy} aria-busy={busy}>
                    {busy && <span className="login-button-spinner" aria-hidden="true" />}
                    <span>{busy ? t("auth.signing_in") : t("auth.login_button")}</span>
                  </button>
                </form>

                <p className="login-security-note">
                  <span className="login-shield-icon" aria-hidden="true" />
                  {t("auth.security_note")}
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="login-visual" dir={i18n.dir()} aria-labelledby="login-visual-heading">
          <div className="login-grid-pattern" aria-hidden="true" />
          <div className="login-visual-glow" aria-hidden="true" />

          <div className="login-visual-content">
            <div className="login-visual-intro">
              <h2 id="login-visual-heading" dir="ltr">
                AutoLine<br />
                <span>Data Studio</span>
              </h2>
              <p>{t("auth.visual_eyebrow")}</p>
              <span className="login-visual-accent" aria-hidden="true" />
            </div>

            <div className="login-visual-stage" aria-hidden="true">
              <span className="login-connector login-connector-one" />
              <span className="login-connector login-connector-two" />
              <span className="login-connector login-connector-three" />
              <span className="login-connector login-connector-four" />
              <span className="login-connector login-connector-five" />
              <span className="login-connector login-connector-six" />
              <span className="login-connector login-connector-seven" />
              <span className="login-connector login-connector-eight" />

              <div className="login-visual-node login-visual-node-engine">
                <span className="login-node-icon"><span className="data-glyph glyph-engine" /></span>
                <span>{t("auth.visual_node_engine")}</span>
              </div>
              <div className="login-visual-node login-visual-node-analytics">
                <span className="login-node-icon"><span className="data-glyph glyph-dashboard" /></span>
                <span>{t("auth.visual_node_analytics")}</span>
              </div>

              <div className="login-visual-node login-visual-node-database">
                <span className="login-node-icon"><span className="data-glyph glyph-database" /></span>
                <span>{t("auth.visual_node_database")}</span>
              </div>
              <div className="login-visual-node login-visual-node-brakes">
                <span className="login-node-icon"><span className="data-glyph glyph-wheel" /></span>
                <span>{t("auth.visual_node_brakes")}</span>
              </div>
              <div className="login-visual-node login-visual-node-transmission">
                <span className="login-node-icon"><span className="data-glyph glyph-pipeline" /></span>
                <span>{t("auth.visual_node_transmission")}</span>
              </div>
              <div className="login-visual-node login-visual-node-battery">
                <span className="login-node-icon"><span className="data-glyph glyph-api" /></span>
                <span>{t("auth.visual_node_battery")}</span>
              </div>
              <div className="login-visual-node login-visual-node-inventory">
                <span className="login-node-icon"><span className="data-glyph glyph-file" /></span>
                <span>{t("auth.visual_node_inventory")}</span>
              </div>
              <div className="login-visual-node login-visual-node-wheels">
                <span className="login-node-icon"><span className="data-glyph glyph-wheel" /></span>
                <span>{t("auth.visual_node_wheels")}</span>
              </div>
              <div className="login-visual-node login-visual-node-kpis">
                <span className="login-node-icon"><span className="data-glyph glyph-dashboard" /></span>
                <span>{t("auth.visual_node_kpis")}</span>
              </div>
              <div className="login-visual-node login-visual-node-reports">
                <span className="login-node-icon"><span className="data-glyph glyph-table" /></span>
                <span>{t("auth.visual_node_reports")}</span>
              </div>

              <div className="login-car-art">
                <svg viewBox="0 0 520 190" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M60 131C92 127 110 116 135 91C163 61 199 42 244 37L317 34C356 35 384 54 411 81L459 97C475 104 485 119 485 135V144H452C448 119 429 102 405 102C380 102 361 119 357 144H173C169 119 150 102 126 102C101 102 82 119 78 144H54C42 144 36 137 39 130Z" />
                  <path d="M157 86C182 58 204 49 240 45L312 44C338 46 360 57 380 78L157 86Z" />
                  <circle cx="126" cy="144" r="30" />
                  <circle cx="405" cy="144" r="30" />
                  <circle cx="126" cy="144" r="17" />
                  <circle cx="405" cy="144" r="17" />
                  <path d="M240 45L242 85M355 52L325 84" />
                </svg>
              </div>

              <div className="login-dashboard">
                <div className="login-dashboard-topline">
                  <div className="login-dashboard-title">
                    <span className="data-glyph glyph-vehicle" />
                    <strong>{t("auth.visual_dashboard_title")}</strong>
                  </div>
                  <span className="login-dashboard-menu"><i /><i /><i /></span>
                </div>

                <div className="login-dashboard-metrics">
                  <div className="login-metric-card">
                    <span>{t("auth.visual_processed")}</span>
                    <strong>2.84M</strong>
                  </div>
                  <div className="login-metric-card">
                    <span>{t("auth.visual_quality")}</span>
                    <strong>98.7%</strong>
                  </div>
                  <div className="login-metric-card">
                    <span>{t("auth.visual_sources")}</span>
                    <strong>12</strong>
                  </div>
                </div>

                <div className="login-data-chart">
                  <div className="login-chart-heading">
                    <span>{t("auth.visual_volume")}</span>
                    {/* dir="ltr" so the sign stays in front of the number. Written the
                        other way round it only reads correctly in Arabic and Hebrew,
                        where bidi moves a trailing "+" to the left; in English it comes
                        out as "24.8%+". */}
                    <strong dir="ltr">+24.8%</strong>
                  </div>
                  <div className="login-chart-bars">
                    <span />
                    <span />
                    <span />
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
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
