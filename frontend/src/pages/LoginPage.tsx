import { useEffect, useRef, useState } from "react";
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
  const [languageMenuOpen, setLanguageMenuOpen] = useState(false);
  const languageMenuRef = useRef<HTMLDivElement>(null);
  const languageTriggerRef = useRef<HTMLButtonElement>(null);
  const activeLanguage = LOGIN_LANGUAGES.some(({ code }) => code === i18n.language.split("-")[0])
    ? i18n.language.split("-")[0]
    : "ar";
  const activeLanguageLabel = LOGIN_LANGUAGES.find(({ code }) => code === activeLanguage)?.label
    ?? LOGIN_LANGUAGES[0].label;

  useEffect(() => {
    if (!languageMenuOpen) return;

    function closeOnOutsidePress(event: PointerEvent) {
      if (!languageMenuRef.current?.contains(event.target as Node)) {
        setLanguageMenuOpen(false);
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setLanguageMenuOpen(false);
        languageTriggerRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", closeOnOutsidePress);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePress);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [languageMenuOpen]);

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
                <div
                  ref={languageMenuRef}
                  className={`login-language-select${languageMenuOpen ? " is-open" : ""}`}
                >
                  <button
                    ref={languageTriggerRef}
                    type="button"
                    className="login-language-trigger"
                    aria-label={t("common.language")}
                    aria-haspopup="menu"
                    aria-expanded={languageMenuOpen}
                    aria-controls="login-language-menu"
                    onClick={() => setLanguageMenuOpen((isOpen) => !isOpen)}
                  >
                    <span className="login-globe-icon" aria-hidden="true" />
                    <span className="login-language-label" dir={i18n.dir()} aria-hidden="true">
                      {activeLanguageLabel}
                    </span>
                    <span className="login-select-chevron" aria-hidden="true" />
                  </button>
                  {languageMenuOpen && (
                    <div id="login-language-menu" className="login-language-menu" role="menu" aria-label={t("common.language")}>
                      {LOGIN_LANGUAGES.map(({ code, label }) => (
                        <button
                          key={code}
                          type="button"
                          className="login-language-option"
                          role="menuitemradio"
                          aria-checked={activeLanguage === code}
                          dir={code === "en" ? "ltr" : "rtl"}
                          onClick={() => {
                            void i18n.changeLanguage(code);
                            setLanguageMenuOpen(false);
                          }}
                        >
                          <span>{label}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
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
          <div className="lv-grid" aria-hidden="true" />
          <div className="lv-glow" aria-hidden="true" />

          <div className="lv-content">
            <header className="lv-intro">
              <span className="lv-eyebrow">{t("auth.visual_eyebrow")}</span>
              <h2 id="login-visual-heading" dir="ltr">
                AutoLine
                <span>Data Studio</span>
              </h2>
              <p>{t("auth.visual_lead")}</p>
            </header>

            <DataCascade />

            <dl className="lv-stats" aria-hidden="true">
              <div>
                <dt>{t("auth.visual_stat_rows")}</dt>
                <dd>4.1M</dd>
              </div>
              <div>
                <dt>{t("auth.visual_stat_columns")}</dt>
                <dd>22</dd>
              </div>
              <div>
                <dt>{t("auth.visual_stat_formats")}</dt>
                <dd>3</dd>
              </div>
            </dl>
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

/**
 * What the product does, in one picture: a file arrives as text, becomes columns, becomes
 * an answer. Three cards cascading forward, the finished one in front.
 *
 * Decoration, so the whole thing is aria-hidden - a screen reader gets the heading and the
 * form, not a table of invented rows. The figures are illustrative and fixed; nothing here
 * is queried, and nobody is signed in yet to query it.
 */
function DataCascade() {
  const { t } = useTranslation();

  // Deliberately unremarkable sample rows. Real registry values would be a small
  // disclosure on a page that anyone can reach without signing in.
  const table = [
    ["10428831", "KIA", "2021"],
    ["10428907", "TOYOTA", "2019"],
    ["10429114", "HYUNDAI", "2022"],
    ["10429260", "MAZDA", "2020"],
  ];

  const bars = [
    { label: "KIA", pct: 100 },
    { label: "TOYOTA", pct: 78 },
    { label: "HYUNDAI", pct: 61 },
    { label: "MAZDA", pct: 44 },
    { label: "SKODA", pct: 29 },
  ];

  return (
    <div className="lv-cascade" aria-hidden="true">
      {/* back - the file exactly as it lands on disk */}
      <figure className="lv-card lv-card-raw">
        <figcaption>{t("auth.visual_step_file")}</figcaption>
        <pre dir="ltr">
          mispar_rechev,tozeret_nm,shnat_yitzur{"\n"}
          10428831,KIA,2021{"\n"}
          10428907,TOYOTA,2019{"\n"}
          10429114,HYUNDAI,2022{"\n"}
          10429260,MAZDA,2020
        </pre>
      </figure>

      {/* middle - the same bytes, understood as columns */}
      <figure className="lv-card lv-card-table">
        <figcaption>{t("auth.visual_step_table")}</figcaption>
        <table dir="ltr">
          <thead>
            <tr>
              <th>mispar_rechev</th>
              <th>tozeret_nm</th>
              <th>shnat</th>
            </tr>
          </thead>
          <tbody>
            {table.map((row) => (
              <tr key={row[0]}>
                {row.map((cell) => (
                  <td key={cell}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </figure>

      {/* front - the reason anyone opened the file */}
      <figure className="lv-card lv-card-chart">
        <figcaption>{t("auth.visual_step_chart")}</figcaption>
        <ul className="lv-bars" dir="ltr">
          {bars.map(({ label, pct }) => (
            <li key={label}>
              <span className="lv-bar-label">{label}</span>
              <span className="lv-bar-track">
                <span className="lv-bar-fill" style={{ width: `${pct}%` }} />
              </span>
            </li>
          ))}
        </ul>
      </figure>
    </div>
  );
}
