import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/** What the user picked. "system" defers to the operating system, and keeps deferring -
 *  changing the OS theme with this selected changes the app live. */
export type ThemeMode = "light" | "dark" | "system";

/** What is actually painted right now. "system" is resolved away. */
export type ResolvedTheme = "light" | "dark";

/** Shared with the inline boot script in index.html - both read and write this key. */
export const THEME_KEY = "theme";

const MEDIA = "(prefers-color-scheme: dark)";

interface ThemeValue {
  mode: ThemeMode;
  resolved: ResolvedTheme;
  setMode: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

function readMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    // localStorage throws in some privacy modes; falling back is better than crashing
  }
  return "system";
}

function systemTheme(): ResolvedTheme {
  return window.matchMedia(MEDIA).matches ? "dark" : "light";
}

/**
 * Owns the app's colour scheme.
 *
 * The resolved theme is written to `data-theme` on <html>, which is what every
 * stylesheet keys off - so a single attribute switches the data workspace, the admin
 * panel and the statistics dashboard together. The charts are canvas rather than CSS and
 * cannot inherit that, so they watch the attribute themselves (see useThemeTokens).
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readMode);
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme);

  // Only matters while the choice is "system", but the listener is cheap and keeping it
  // always attached avoids a stale reading the moment someone switches back to it.
  useEffect(() => {
    const media = window.matchMedia(MEDIA);
    const update = () => setSystem(media.matches ? "dark" : "light");
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const resolved: ResolvedTheme = mode === "system" ? system : mode;

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolved);
  }, [resolved]);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // the choice still applies for this session, it just will not be remembered
    }
  }, []);

  const value = useMemo(() => ({ mode, resolved, setMode }), [mode, resolved, setMode]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
