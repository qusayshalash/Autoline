import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  Car,
  CarFront,
  ChartNoAxesColumnIncreasing,
  ChevronDown,
  Cloud,
  Cpu,
  Database,
  Eye,
  EyeOff,
  Globe,
  ListFilter,
  Moon,
  PieChart,
  ScanSearch,
  Settings,
  ShieldCheck,
  Sun,
  UserRound,
  Workflow,
  Wrench,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";
import "./LoginPage.css";

const REMEMBERED_IDENTIFIER_KEY = "data-workspace-identifier";

const LANGUAGES = [
  { code: "ar", label: "العربية" },
  { code: "en", label: "English" },
  { code: "he", label: "עברית" },
] as const;

function readRemembered(): string {
  try {
    return window.localStorage.getItem(REMEMBERED_IDENTIFIER_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeRemembered(identifier: string, keep: boolean) {
  try {
    if (keep) window.localStorage.setItem(REMEMBERED_IDENTIFIER_KEY, identifier);
    else window.localStorage.removeItem(REMEMBERED_IDENTIFIER_KEY);
  } catch {
    // Signing in has to work when storage does not.
  }
}

/** Retry-After arrives in seconds; a wait is easier to act on stated in minutes. */
function retryMinutes(err: unknown): number {
  const header = (err as { response?: { headers?: Record<string, string> } })?.response
    ?.headers?.["retry-after"];
  const seconds = Number(header);
  return Number.isFinite(seconds) && seconds > 0 ? Math.max(1, Math.ceil(seconds / 60)) : 1;
}

/**
 * Sign-in.
 *
 * The right-hand panel is decoration - a car, some instruments, a pipeline - and it says
 * so: the whole thing is aria-hidden, so a screen reader is read the form and the
 * heading rather than thirty ornamental labels. The figures on it are illustrative and
 * fixed; they are not this workspace's data, and nothing here queries anything.
 *
 * Below 960px the panel is dropped rather than reflowed. It is the part of the page that
 * carries no information, so on a phone it is the part that goes.
 */
export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login, user } = useAuth();
  const { resolved, setMode } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  const [identifier, setIdentifier] = useState(readRemembered);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(() => Boolean(readRemembered()));
  const [tried, setTried] = useState(false);

  const base = i18n.language.split("-")[0];
  const language = LANGUAGES.some((l) => l.code === base) ? base : "ar";
  const languageLabel = LANGUAGES.find((l) => l.code === language)?.label ?? LANGUAGES[0].label;
  const isDark = resolved === "dark";

  if (user) return <Navigate to="/" replace />;

  const missingIdentifier = tried && !identifier.trim();
  const missingPassword = tried && !password;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTried(true);
    setError(null);
    setNotice(null);

    const name = identifier.trim();
    if (!name || !password) return;

    setBusy(true);
    try {
      await login(name, password);
      writeRemembered(name, remember);
      const from = (location.state as { from?: string })?.from ?? "/";
      navigate(from, { replace: true });
    } catch (err) {
      // 429 is the one refusal worth explaining. Every other failure stays deliberately
      // vague - saying which half of the pair was wrong tells an attacker which usernames
      // exist - but "you are locked out" is something the person at the screen needs,
      // otherwise a correct password appearing to fail looks like a broken system.
      const status = (err as { response?: { status?: number } })?.response?.status;
      setError(
        status === 429
          ? t("auth.too_many_attempts", { minutes: retryMinutes(err) })
          : t("auth.login_error")
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <section className="login-section" dir={i18n.dir()}>
        <header className="login-header">
          <div className="login-brand">
            <div className="login-brand-logo" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
            </div>
            <div className="login-brand-name" lang="en">
              <strong>AutoLine</strong>
              <small>Data Studio</small>
            </div>
          </div>

          <div className="login-header-controls">
            {/* A real <select> laid transparently over the button: the eye gets the
                design, the keyboard and the phone get the native picker. */}
            <div className="login-language">
              <div className="login-control-btn" aria-hidden="true">
                <Globe />
                <span className="login-language-text">{languageLabel}</span>
                <ChevronDown />
              </div>
              <select
                aria-label={t("common.language")}
                value={language}
                onChange={(e) => void i18n.changeLanguage(e.currentTarget.value)}
              >
                {LANGUAGES.map(({ code, label }) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              className="login-theme-btn"
              onClick={() => setMode(isDark ? "light" : "dark")}
              aria-label={t(isDark ? "theme.light" : "theme.dark")}
              title={t(isDark ? "theme.light" : "theme.dark")}
            >
              {isDark ? <Sun /> : <Moon />}
            </button>
          </div>
        </header>

        <main className="login-content">
          <div className="login-card">
            <p className="login-secure-label">
              <span className="login-secure-dot" aria-hidden="true" />
              {t("auth.secure_access")}
            </p>

            <h1 className="login-welcome-title">{t("auth.welcome_back")}</h1>
            <p className="login-welcome-text">{t("auth.login_subtitle")}</p>

            <form className="login-form" onSubmit={handleSubmit} noValidate>
              {error && (
                <div className="login-alert login-alert-error" role="alert">
                  <p>{error}</p>
                </div>
              )}
              {notice && (
                <div className="login-alert login-alert-notice" role="status">
                  <p>{notice}</p>
                </div>
              )}

              <div className="login-field-group">
                <label className="login-field-label" htmlFor="login-identifier">
                  {t("auth.identifier")}
                </label>
                <div className="login-input-wrapper">
                  <UserRound className="login-field-icon" aria-hidden="true" />
                  <input
                    id="login-identifier"
                    type="text"
                    inputMode="email"
                    autoComplete="username"
                    placeholder={t("auth.identifier_placeholder")}
                    value={identifier}
                    onChange={(e) => {
                      setIdentifier(e.target.value);
                      setError(null);
                      setNotice(null);
                    }}
                    aria-invalid={missingIdentifier}
                    aria-describedby={missingIdentifier ? "login-identifier-error" : undefined}
                    autoFocus
                  />
                </div>
                {missingIdentifier && (
                  <p className="login-error" id="login-identifier-error">
                    {t("auth.identifier_required")}
                  </p>
                )}
              </div>

              <div className="login-field-group">
                <div className="login-password-row">
                  <label className="login-field-label" htmlFor="login-password">
                    {t("auth.password")}
                  </label>
                  <button
                    type="button"
                    className="login-forgot"
                    onClick={() => {
                      setNotice(t("auth.reset_hint"));
                      setError(null);
                    }}
                  >
                    {t("auth.forgot_password")}
                  </button>
                </div>

                <div className="login-input-wrapper">
                  <input
                    id="login-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder={t("auth.password_placeholder")}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setError(null);
                      setNotice(null);
                    }}
                    aria-invalid={missingPassword}
                    aria-describedby={missingPassword ? "login-password-error" : undefined}
                  />
                  <button
                    type="button"
                    className="login-field-action-btn"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={t(showPassword ? "common.hide_password" : "common.show_password")}
                    aria-pressed={showPassword}
                    title={t(showPassword ? "common.hide_password" : "common.show_password")}
                  >
                    {showPassword ? <Eye aria-hidden="true" /> : <EyeOff aria-hidden="true" />}
                  </button>
                </div>
                {missingPassword && (
                  <p className="login-error" id="login-password-error">
                    {t("auth.password_required")}
                  </p>
                )}
              </div>

              <div className="login-remember-row">
                <label className="login-check">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                  />
                  <span className="login-check-box" aria-hidden="true" />
                  <span>{t("auth.remember_identifier")}</span>
                </label>
              </div>

              <button className="login-signin-btn" type="submit" disabled={busy} aria-busy={busy}>
                {busy ? t("auth.signing_in") : t("auth.login_button")}
              </button>

              <p className="login-enterprise-note">
                <ShieldCheck aria-hidden="true" />
                {t("auth.security_note")}
              </p>
            </form>
          </div>
        </main>
      </section>

      <VisualPanel />
    </div>
  );
}

/** Ornament. Hidden from assistive technology in full - see the note on LoginPage. */
function VisualPanel() {
  const { t, i18n } = useTranslation();

  const network = [
    { Icon: CarFront, key: "vehicles" },
    { Icon: Activity, key: "sensors" },
    { Icon: Cpu, key: "ecu" },
    { Icon: ScanSearch, key: "diagnostics" },
    { Icon: Wrench, key: "maintenance" },
  ] as const;

  const tools = [
    { Icon: ChartNoAxesColumnIncreasing, key: "analytics" },
    { Icon: PieChart, key: "reports" },
    { Icon: ListFilter, key: "filters" },
    { Icon: Cloud, key: "cloud" },
  ] as const;

  const pipeline = [
    { Icon: Database, key: "database" },
    { Icon: Car, key: "collect" },
    { Icon: Settings, key: "process" },
    { Icon: Workflow, key: "transform" },
    { Icon: ChartNoAxesColumnIncreasing, key: "visualise" },
  ] as const;

  return (
    <section className="login-visual" dir={i18n.dir()} aria-hidden="true">
      {[
        { left: "13%", top: "14%", delay: "0s" },
        { left: "34%", top: "22%", delay: ".6s" },
        { left: "73%", top: "11%", delay: "1.4s" },
        { left: "88%", top: "47%", delay: ".9s" },
        { left: "25%", top: "76%", delay: "1.7s" },
      ].map((p, i) => (
        <span
          key={i}
          className="login-particle"
          style={{ left: p.left, top: p.top, animationDelay: p.delay }}
        />
      ))}

      <div className="login-visual-content">
        <div className="login-top-network">
          {network.map(({ Icon, key }) => (
            <div className="login-network-item" key={key}>
              <div className="login-data-icon">
                <Icon />
              </div>
              <span>{t(`auth.node_${key}`)}</span>
            </div>
          ))}
        </div>

        <div className="login-vehicle-stage">
          <div className="login-vin-card">
            <div className="login-vin-row">
              <span>VIN</span>
              <strong>WBASA7C50GG123456</strong>
            </div>
            <div className="login-vin-row">
              <span>{t("auth.vin_model")}</span>
              <strong>Sedan 4.0L</strong>
            </div>
            <div className="login-vin-row">
              <span>{t("auth.vin_year")}</span>
              <strong>2022</strong>
            </div>
          </div>

          <CarArt />

          <div className="login-side-tools">
            {tools.map(({ Icon, key }) => (
              <div className="login-side-tool" key={key}>
                <div className="login-data-icon">
                  <Icon />
                </div>
                <p>{t(`auth.tool_${key}`)}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="login-analytics-grid">
          <article className="login-analytics-card">
            <h3>{t("auth.card_performance")}</h3>
            <span className="login-metric-label">{t("auth.metric_engine_load")}</span>
            <strong className="login-metric-value">78%</strong>
            <div className="login-line-chart">
              <svg viewBox="0 0 250 65" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="loginChartGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#078fff" stopOpacity=".32" />
                    <stop offset="100%" stopColor="#078fff" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <polygon
                  fill="url(#loginChartGradient)"
                  points="0,60 0,54 18,45 34,49 51,30 70,38 91,22 109,34 125,20 143,27 163,5 181,21 200,17 219,8 250,25 250,65"
                />
                <path d="M0 54 L18 45 L34 49 L51 30 L70 38 L91 22 L109 34 L125 20 L143 27 L163 5 L181 21 L200 17 L219 8 L250 25" />
              </svg>
            </div>
          </article>

          <article className="login-analytics-card">
            <h3>{t("auth.card_fuel")}</h3>
            <div className="login-gauge">
              <div className="login-gauge-ring" />
              <div className="login-gauge-value">
                24.6
                <small>{t("auth.unit_km_per_litre")}</small>
              </div>
            </div>
          </article>

          <article className="login-analytics-card">
            <h3>{t("auth.card_health")}</h3>
            <div className="login-health-layout">
              <div className="login-health-ring">92%</div>
              <ul className="login-health-list">
                <li>{t("auth.part_engine")}</li>
                <li>{t("auth.part_transmission")}</li>
                <li>{t("auth.part_brakes")}</li>
                <li>{t("auth.part_battery")}</li>
              </ul>
            </div>
          </article>
        </div>

        <div className="login-pipeline">
          {pipeline.map(({ Icon, key }, i) => (
            <PipelineStep key={key} withLine={i < pipeline.length - 1}>
              <div className="login-pipe-node">
                <div className="login-data-icon">
                  <Icon />
                </div>
                <p>{t(`auth.pipe_${key}`)}</p>
              </div>
            </PipelineStep>
          ))}
        </div>

        <div className="login-bottom-grid">
          <div className="login-bottom-card">
            <h4>{t("auth.card_files")}</h4>
            <div className="login-file-list">
              {[
                ["CSV", "CSV"],
                ["XLS", "XLSX"],
                ["{ }", "JSON"],
                ["</>", "XML"],
                ["DB", "SQL"],
              ].map(([mark, name]) => (
                <div className="login-file" key={name}>
                  <div className="login-file-icon">{mark}</div>
                  {name}
                </div>
              ))}
            </div>
          </div>

          <div className="login-bottom-card">
            <h4>{t("auth.card_queries")}</h4>
            <pre className="login-sql">{`SELECT * FROM vehicle_data
WHERE date >= '2026-01-01'
ORDER BY timestamp DESC;`}</pre>
          </div>

          <div className="login-bottom-card">
            <h4>{t("auth.card_insights")}</h4>
            <div className="login-insights">
              <div className="login-bar" />
              <div className="login-bar" />
              <div className="login-bar" />
              <div className="login-bar" />
              <div className="login-bar" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/** A pipeline node, plus the connector that follows it unless it is the last. */
function PipelineStep({
  children,
  withLine,
}: {
  children: React.ReactNode;
  withLine: boolean;
}) {
  return (
    <>
      {children}
      {withLine && <div className="login-pipe-line" />}
    </>
  );
}

function CarArt() {
  return (
    <svg className="login-car" viewBox="0 0 760 330" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="loginCarBody" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#0b3970" stopOpacity=".28" />
          <stop offset="100%" stopColor="#021c3c" stopOpacity=".65" />
        </linearGradient>
        <linearGradient id="loginWheelGlow" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#23c8ff" />
          <stop offset="100%" stopColor="#1260ff" />
        </linearGradient>
      </defs>

      <ellipse cx="390" cy="283" rx="280" ry="25" fill="#006cff" opacity=".07" />

      <path
        d="M105 220 C118 180 147 162 200 151 L281 95 C310 76 346 67 390 67 L500 67 C539 69 577 88 609 119 L651 161 C681 172 701 192 704 218 L697 246 L651 255 C642 218 615 191 576 191 C536 191 508 217 501 258 L253 258 C246 218 216 191 178 191 C138 191 109 217 102 252 L72 243 C72 233 81 225 105 220 Z"
        fill="url(#loginCarBody)"
        stroke="#2c9cff"
        strokeWidth="2"
      />

      <path
        d="M289 104 C314 88 344 82 382 82 L417 82 L416 145 L236 145 Z"
        fill="#041d3a"
        stroke="#42a8ff"
        strokeWidth="1.4"
      />
      <path
        d="M430 82 L492 83 C526 87 554 101 580 127 L596 145 L432 145 Z"
        fill="#041d3a"
        stroke="#42a8ff"
        strokeWidth="1.4"
      />

      <g stroke="#168eff" opacity=".37" strokeWidth="1">
        <path d="M142 173 L617 173" />
        <path d="M118 196 L654 196" />
        <path d="M103 220 L684 220" />
        <path d="M243 145 L231 245" />
        <path d="M420 145 L420 252" />
        <path d="M596 146 L613 195" />
      </g>

      <g>
        <circle cx="178" cy="245" r="50" fill="#02162e" stroke="#258cff" strokeWidth="3" />
        <circle cx="178" cy="245" r="34" fill="none" stroke="#175aa5" strokeWidth="4" />
        <circle cx="178" cy="245" r="9" fill="url(#loginWheelGlow)" />
        <circle cx="578" cy="245" r="50" fill="#02162e" stroke="#258cff" strokeWidth="3" />
        <circle cx="578" cy="245" r="34" fill="none" stroke="#175aa5" strokeWidth="4" />
        <circle cx="578" cy="245" r="9" fill="url(#loginWheelGlow)" />
      </g>

      <path d="M115 191 L190 174 L199 187 L134 204 Z" fill="#41bdff" opacity=".65" />
      <path d="M649 177 L678 191 L675 203 L642 194 Z" fill="#147fff" opacity=".45" />

      <g fill="#18a9ff">
        <circle cx="340" cy="184" r="5" />
        <circle cx="465" cy="186" r="5" />
        <circle cx="520" cy="160" r="4" />
        <circle cx="278" cy="201" r="4" />
      </g>

      <g transform="translate(200 157)" stroke="#24b7ff" strokeWidth="1" opacity=".75">
        <rect x="0" y="0" width="75" height="46" rx="7" fill="#0874ff" fillOpacity=".14" />
        <path d="M15 9 H60 V36 H15 Z" fill="none" />
        <path d="M26 3 V42" />
        <path d="M48 3 V42" />
      </g>
    </svg>
  );
}
