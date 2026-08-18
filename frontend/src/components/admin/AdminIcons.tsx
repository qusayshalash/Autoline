/** Icon set for the admin panel. One visual family, so the sidebar reads as a unit. */

const base = {
  width: 18,
  height: 18,
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function IconOverview() {
  return (
    <svg {...base}>
      <rect x="2.5" y="2.5" width="6.5" height="6.5" rx="1.5" />
      <rect x="11" y="2.5" width="6.5" height="6.5" rx="1.5" />
      <rect x="2.5" y="11" width="6.5" height="6.5" rx="1.5" />
      <rect x="11" y="11" width="6.5" height="6.5" rx="1.5" />
    </svg>
  );
}

export function IconUsers() {
  return (
    <svg {...base}>
      <circle cx="7.5" cy="7" r="2.8" />
      <path d="M2.5 16.5c0-2.5 2.2-4.2 5-4.2s5 1.7 5 4.2" />
      <path d="M13.5 5.2a2.6 2.6 0 0 1 0 5M14.5 12.6c2 .5 3 1.9 3 3.9" />
    </svg>
  );
}

export function IconShield() {
  return (
    <svg {...base}>
      <path d="M10 2.2l6 2.4v5c0 3.6-2.5 6.3-6 7.2-3.5-.9-6-3.6-6-7.2v-5z" />
      <path d="M7.6 10l1.7 1.7 3.2-3.4" />
    </svg>
  );
}

export function IconGlobe() {
  return (
    <svg {...base}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M2.5 10h15M10 2.5c2 2.2 3 4.7 3 7.5s-1 5.3-3 7.5c-2-2.2-3-4.7-3-7.5s1-5.3 3-7.5z" />
    </svg>
  );
}

export function IconFiles() {
  return (
    <svg {...base}>
      <path d="M3 5.5A1.5 1.5 0 0 1 4.5 4h3l1.5 2h6.5A1.5 1.5 0 0 1 17 7.5v7A1.5 1.5 0 0 1 15.5 16h-11A1.5 1.5 0 0 1 3 14.5z" />
    </svg>
  );
}

export function IconActivity() {
  return (
    <svg {...base}>
      <path d="M2.5 10.5h3l2-5.5 3.5 11 2.5-6.5h4" />
    </svg>
  );
}

export function IconSettings() {
  return (
    <svg {...base}>
      <circle cx="10" cy="10" r="2.6" />
      <path d="M10 2.5v2M10 15.5v2M17.5 10h-2M4.5 10h-2M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4M15.3 15.3l-1.4-1.4M6.1 6.1L4.7 4.7" />
    </svg>
  );
}

export function IconPanel() {
  return (
    <svg {...base}>
      <rect x="2.5" y="3.5" width="15" height="13" rx="2" />
      <path d="M8 3.5v13" />
    </svg>
  );
}

export function IconBack() {
  return (
    <svg {...base}>
      <path d="M12 4l-5 6 5 6" />
    </svg>
  );
}

export function IconSearch() {
  return (
    <svg {...base}>
      <circle cx="9" cy="9" r="5.5" />
      <path d="M13 13l4 4" />
    </svg>
  );
}

export function IconPlus() {
  return (
    <svg {...base}>
      <path d="M10 4.5v11M4.5 10h11" />
    </svg>
  );
}

export function IconClose() {
  return (
    <svg {...base}>
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  );
}

export function IconTrash() {
  return (
    <svg {...base}>
      <path d="M3 5.5h14M7.5 5.5V3.8h5v1.7" />
      <path d="M5 5.5l.8 10.2A1.3 1.3 0 0 0 7.1 17h5.8a1.3 1.3 0 0 0 1.3-1.3L15 5.5" />
    </svg>
  );
}

export function IconKey() {
  return (
    <svg {...base}>
      <circle cx="6.5" cy="6.5" r="3.5" />
      <path d="M9 9l7 7M13 13l1.6-1.6M15.5 15.5l1.6-1.6" />
    </svg>
  );
}

export function IconDatabase() {
  return (
    <svg {...base}>
      <ellipse cx="10" cy="5" rx="6.5" ry="2.5" />
      <path d="M3.5 5v10c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5V5" />
      <path d="M3.5 10c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5" />
    </svg>
  );
}
