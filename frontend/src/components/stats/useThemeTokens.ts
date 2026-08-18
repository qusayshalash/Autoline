import { useEffect, useState } from "react";

export interface ThemeTokens {
  text: string;
  muted: string;
  border: string;
  surface: string;
  bg: string;
}

function read(): ThemeTokens {
  const style = getComputedStyle(document.documentElement);
  const get = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    text: get("--text", "#12141c"),
    muted: get("--text-muted", "#676c7a"),
    border: get("--border", "#e2e4e9"),
    surface: get("--surface", "#ffffff"),
    bg: get("--bg", "#f7f8fa"),
  };
}

/**
 * The app's theme colours, as values rather than CSS.
 *
 * ECharts paints onto a canvas, so it cannot inherit `var(--text)` the way the rest of
 * the dashboard does - axis labels and tooltips have to be given real colours. Reading
 * them from the same custom properties keeps one palette rather than two.
 *
 * The trigger to re-read is the `data-theme` attribute rather than the OS preference:
 * the theme can now be chosen in the app, so watching `prefers-color-scheme` alone would
 * leave the charts painted for the old theme after a manual switch. Watching the
 * attribute covers both, since ThemeContext writes it either way.
 */
export function useThemeTokens(): ThemeTokens {
  const [tokens, setTokens] = useState<ThemeTokens>(read);

  useEffect(() => {
    const update = () => setTokens(read());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  return tokens;
}
