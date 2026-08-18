import { useEffect, useState } from "react";

import type { Brand } from "../../data/brandRegistry";
import { brandLogoUrl } from "../../data/brandRegistry";

/**
 * A manufacturer's mark, in three tiers.
 *
 * 1. A real logo file at /brands/<slug>.svg, if one has been added.
 * 2. Otherwise a monogram tile in the marque's own colour - a recognised brand still
 *    looks like itself even with no artwork on disk.
 * 3. An unrecognised manufacturer gets a neutral car badge with its first letter.
 *
 * The image is probed rather than rendered directly so a missing file never flashes a
 * broken-image icon, and the probe is fire-and-forget: statistics render immediately and
 * the logo swaps in if and when it loads. Results are remembered for the session, so
 * repeat renders of the same brand don't re-probe.
 */

type ProbeState = "loading" | "ok" | "missing";

const probed = new Map<string, ProbeState>();

function useLogo(url: string | null): ProbeState {
  const [state, setState] = useState<ProbeState>(() =>
    url ? probed.get(url) ?? "loading" : "missing"
  );

  useEffect(() => {
    if (!url) return;
    const known = probed.get(url);
    if (known && known !== "loading") {
      setState(known);
      return;
    }

    let live = true;
    const img = new Image();
    const settle = (result: ProbeState) => {
      probed.set(url, result);
      if (live) setState(result);
    };
    img.onload = () => settle("ok");
    img.onerror = () => settle("missing");
    img.src = url;

    return () => {
      live = false;
    };
  }, [url]);

  return state;
}

interface Props {
  brand?: Brand;
  /** the raw value, used for the initial when the brand isn't recognised */
  label: string;
  size?: number;
}

export default function BrandLogo({ brand, label, size = 44 }: Props) {
  const url = brand ? brandLogoUrl(brand) : null;
  const state = useLogo(url);

  const style = { width: size, height: size, fontSize: Math.round(size * 0.4) };

  if (brand && state === "ok" && url) {
    return (
      <span className="brand-logo has-art" style={style}>
        <img src={url} alt="" />
      </span>
    );
  }

  if (brand) {
    const initials = brand.en.replace(/[^A-Za-z]/g, "").slice(0, 3).toUpperCase();
    return (
      <span
        className="brand-logo monogram"
        style={{ ...style, background: brand.color, fontSize: Math.round(size * 0.3) }}
        title={brand.en}
      >
        {initials}
      </span>
    );
  }

  return (
    <span className="brand-logo generic" style={style} title={label}>
      <CarBadge />
      <em>{(label.trim()[0] ?? "?").toUpperCase()}</em>
    </span>
  );
}

function CarBadge() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M5 11l1.5-4A2 2 0 0 1 8.4 5.7h7.2a2 2 0 0 1 1.9 1.3L19 11" strokeLinecap="round" />
      <rect x="3" y="11" width="18" height="6" rx="1.6" />
      <circle cx="7.5" cy="17" r="1.6" />
      <circle cx="16.5" cy="17" r="1.6" />
    </svg>
  );
}
