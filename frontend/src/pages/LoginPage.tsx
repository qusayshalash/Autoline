import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { columnLabel } from "../data/columnDictionary";
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
              <Figure label={t("auth.visual_stat_rows")} to={24_800_000} format={millions} />
              <Figure label={t("auth.visual_stat_columns")} to={148} />
              <Figure label={t("auth.visual_stat_volume")} to={826} format={gigabytes} />
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

/* ---------------------------------------------------------------------------
   The panel's moving parts
   --------------------------------------------------------------------------- */

/** One pass over the file, asking one question of it. */
interface Scene {
  /** Raw header names, exactly as they appear in the file. */
  columns: [string, string, string];
  /** Four rows, in the same order as the columns. */
  rows: [string, string, string][];
  /** What the breakdown of the middle column looks like. */
  bars: { label: string; pct: number }[];
}

/**
 * Four questions over the same registry export. Rotating through them is what makes the
 * panel look alive; each one is internally consistent, so the raw text, the table and the
 * chart are always three views of the same thing rather than three unrelated pictures.
 *
 * The values are invented. Real registry figures on a page anyone can reach without
 * signing in would be a small disclosure, and an illustration does not need them.
 */
const SCENES: Scene[] = [
  {
    columns: ["mispar_rechev", "tozeret_nm", "shnat_yitzur"],
    rows: [
      ["10428831", "KIA", "2021"],
      ["10428907", "TOYOTA", "2019"],
      ["10429114", "HYUNDAI", "2022"],
      ["10429260", "MAZDA", "2020"],
    ],
    bars: [
      { label: "KIA", pct: 100 },
      { label: "TOYOTA", pct: 78 },
      { label: "HYUNDAI", pct: 61 },
      { label: "MAZDA", pct: 44 },
      { label: "SKODA", pct: 29 },
    ],
  },
  {
    columns: ["mispar_rechev", "degem_nm", "shnat_yitzur"],
    rows: [
      ["10431044", "SPORTAGE", "2022"],
      ["10431190", "COROLLA", "2021"],
      ["10431358", "TUCSON", "2023"],
      ["10431476", "CX-5", "2020"],
    ],
    bars: [
      { label: "SPORTAGE", pct: 100 },
      { label: "COROLLA", pct: 91 },
      { label: "TUCSON", pct: 67 },
      { label: "CX-5", pct: 52 },
      { label: "OCTAVIA", pct: 38 },
    ],
  },
  {
    columns: ["mispar_rechev", "sug_delek_nm", "shnat_yitzur"],
    rows: [
      ["10433612", "PETROL", "2018"],
      ["10433784", "DIESEL", "2021"],
      ["10433905", "HYBRID", "2023"],
      ["10434027", "ELECTRIC", "2024"],
    ],
    bars: [
      { label: "PETROL", pct: 100 },
      { label: "HYBRID", pct: 46 },
      { label: "DIESEL", pct: 33 },
      { label: "ELECTRIC", pct: 21 },
      { label: "LPG", pct: 8 },
    ],
  },
  {
    columns: ["mispar_rechev", "tzeva_rechev", "shnat_yitzur"],
    rows: [
      ["10436128", "WHITE", "2022"],
      ["10436244", "SILVER", "2019"],
      ["10436391", "BLACK", "2021"],
      ["10436507", "GREY", "2023"],
    ],
    bars: [
      { label: "WHITE", pct: 100 },
      { label: "SILVER", pct: 74 },
      { label: "BLACK", pct: 58 },
      { label: "GREY", pct: 41 },
      { label: "BLUE", pct: 26 },
    ],
  },
];

const SCENE_MS = 4600;

/** Whether the reader has asked the system for less movement. Watched rather than read
 *  once, because the setting can change while the page is open. */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return reduced;
}

/**
 * What the product does, in one picture: a file arrives as text, becomes columns, becomes
 * an answer. Three cards cascading forward, the finished one in front.
 *
 * The three cards cycle together through four questions, so the panel reads as something
 * running rather than a screenshot. The cycling stops entirely when the system asks for
 * reduced motion - a login form is a bad place to argue with that - and the first scene
 * simply stays put.
 *
 * The middle card is where the point is made: the back card shows the file's own header
 * names, and the same columns appear in the card in front of it under the names a person
 * uses, taken from the dictionary the rest of the app reads. In Hebrew that dictionary
 * deliberately returns the raw headers, because there they already are the readable ones.
 *
 * Decoration, so the whole thing is aria-hidden - a screen reader gets the heading and the
 * form, not a table of invented rows that changes under it every few seconds.
 */
function DataCascade() {
  const { t, i18n } = useTranslation();
  const reduced = usePrefersReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reduced) return;
    const id = window.setInterval(
      () => setIndex((current) => (current + 1) % SCENES.length),
      SCENE_MS
    );
    return () => window.clearInterval(id);
  }, [reduced]);

  const scene = SCENES[index];
  const analysed = columnLabel(scene.columns[1], i18n.language);
  const csv = [scene.columns.join(","), ...scene.rows.map((row) => row.join(","))].join("\n");

  return (
    <div className="lv-cascade" aria-hidden="true">
      {/* back - the file exactly as it landed, header names and all */}
      <figure className="lv-card lv-card-raw">
        <figcaption>{t("auth.visual_step_file")}</figcaption>
        <pre dir="ltr" key={index}>
          {csv}
        </pre>
      </figure>

      {/* middle - the same bytes, under names a person uses */}
      <figure className="lv-card lv-card-table">
        <figcaption>{t("auth.visual_step_table")}</figcaption>
        <table dir={i18n.dir()}>
          <thead>
            <tr key={index}>
              {scene.columns.map((column) => (
                <th key={column}>{columnLabel(column, i18n.language)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scene.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>
                    <span key={`${index}-${cell}`} dir="ltr">
                      {cell}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </figure>

      {/* front - the reason anyone opened the file */}
      <figure className="lv-card lv-card-chart">
        <figcaption>
          <span>{t("auth.visual_step_chart")}</span>
          <span className="lv-analysed" key={index}>
            {analysed}
          </span>
        </figcaption>
        <ul className="lv-bars" dir="ltr">
          {/* The list items are stable across scenes on purpose: remounting them would
              make each bar appear at its final width instead of growing into it. */}
          {scene.bars.map((bar, barIndex) => (
            <li key={barIndex}>
              <span className="lv-bar-label" key={`${index}-${bar.label}`}>
                {bar.label}
              </span>
              <span className="lv-bar-track">
                <span className="lv-bar-fill" style={{ width: `${bar.pct}%` }} />
              </span>
            </li>
          ))}
        </ul>
      </figure>
    </div>
  );
}

/* ---------------------------------------------------------------------------
   The three figures
   --------------------------------------------------------------------------- */

/** Whole millions to one place: 4_114_487 reads as "4.1M". */
function millions(value: number): string {
  return `${(value / 1_000_000).toFixed(1)}M`;
}

function gigabytes(value: number): string {
  return `${Math.round(value)}GB`;
}

function whole(value: number): string {
  return String(Math.round(value));
}

const COUNT_MS = 1600;

/**
 * Counts from zero to `target` once, on mount.
 *
 * Eased out rather than linear: a figure that decelerates into place reads as landing on
 * a number, while a linear one reads as a clock that happened to stop. Driven by
 * requestAnimationFrame rather than a timer, so it keeps step with the display's refresh
 * and stops being scheduled at all while the tab is in the background.
 *
 * Returns the target immediately when the system asks for reduced motion - the figure is
 * the information, the counting is only decoration on top of it.
 */
function useCountUp(target: number): number {
  const reduced = usePrefersReducedMotion();
  const [value, setValue] = useState(reduced ? target : 0);

  useEffect(() => {
    if (reduced) {
      setValue(target);
      return;
    }
    let frame = 0;
    let start: number | null = null;
    const step = (now: number) => {
      start ??= now;
      const progress = Math.min(1, (now - start) / COUNT_MS);
      // ease-out cubic
      setValue(target * (1 - Math.pow(1 - progress, 3)));
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, reduced]);

  return value;
}

/** One figure in the row beneath the cascade. */
function Figure({
  label,
  to,
  format = whole,
}: {
  label: string;
  to: number;
  format?: (value: number) => string;
}) {
  const value = useCountUp(to);
  return (
    <div>
      <dt>{label}</dt>
      <dd>{format(value)}</dd>
    </div>
  );
}
