import type { ReactElement } from "react";
import { useTranslation } from "react-i18next";

import type { ThemeMode } from "../theme/ThemeContext";
import { useTheme } from "../theme/ThemeContext";

const icon = {
  width: 15,
  height: 15,
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function IconSun() {
  return (
    <svg {...icon}>
      <circle cx="10" cy="10" r="3.4" />
      <path d="M10 2.5v1.8M10 15.7v1.8M17.5 10h-1.8M4.3 10H2.5M15.3 4.7l-1.3 1.3M6 14l-1.3 1.3M15.3 15.3L14 14M6 6L4.7 4.7" />
    </svg>
  );
}

function IconMoon() {
  return (
    <svg {...icon}>
      <path d="M16.5 11.8A6.8 6.8 0 0 1 8.2 3.5a6.9 6.9 0 1 0 8.3 8.3z" />
    </svg>
  );
}

function IconSystem() {
  return (
    <svg {...icon}>
      <rect x="2.6" y="3.8" width="14.8" height="10" rx="1.6" />
      <path d="M7 17h6M10 13.8V17" />
    </svg>
  );
}

const OPTIONS: { mode: ThemeMode; Icon: () => ReactElement }[] = [
  { mode: "light", Icon: IconSun },
  { mode: "dark", Icon: IconMoon },
  { mode: "system", Icon: IconSystem },
];

/**
 * Light / dark / system, as a segmented control.
 *
 * Three states rather than a switch, because "follow the system" is a real preference
 * and a two-way toggle silently throws it away the first time it is touched. The same
 * component sits in all three shells, so the control is in the same place whichever part
 * of the app you are in.
 */
export default function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { t } = useTranslation();
  const { mode, setMode } = useTheme();

  return (
    <div
      className={collapsed ? "theme-toggle collapsed" : "theme-toggle"}
      role="radiogroup"
      aria-label={t("theme.label") ?? "Theme"}
    >
      {OPTIONS.map(({ mode: value, Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={mode === value}
          className={mode === value ? "active" : ""}
          onClick={() => setMode(value)}
          title={t(`theme.${value}`) ?? value}
        >
          <Icon />
          {!collapsed && <span>{t(`theme.${value}`)}</span>}
        </button>
      ))}
    </div>
  );
}
