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

/* --- settings page --- */

export function IconHardDrive() {
  return (
    <svg {...base}>
      <path d="M2.5 11.5h15" />
      <path d="M4.6 3.5h10.8l2.1 8v4a1 1 0 0 1-1 1h-14a1 1 0 0 1-1-1v-4z" />
      <path d="M5.5 14.5h.01M8.5 14.5h.01" />
    </svg>
  );
}

export function IconArchive() {
  return (
    <svg {...base}>
      <rect x="2.5" y="3" width="15" height="3.5" rx="1" />
      <path d="M4 6.5v9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-9" />
      <path d="M8 10h4" />
    </svg>
  );
}

export function IconBroom() {
  return (
    <svg {...base}>
      <path d="M12.5 2.5l5 5" />
      <path d="M11 4l5 5-4.5 4.5-5-5z" />
      <path d="M6.5 8.5L2.5 17.5l9-4" />
    </svg>
  );
}

export function IconClock() {
  return (
    <svg {...base}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M10 5.8V10l2.8 1.7" />
    </svg>
  );
}

export function IconRefresh() {
  return (
    <svg {...base}>
      <path d="M17 10a7 7 0 1 1-2.05-4.95" />
      <path d="M17 3v3.5h-3.5" />
    </svg>
  );
}

export function IconInfo() {
  return (
    <svg {...base}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M10 9.2v4.3M10 6.6h.01" />
    </svg>
  );
}

export function IconCheckCircle() {
  return (
    <svg {...base}>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M6.8 10.2l2.2 2.2 4.2-4.4" />
    </svg>
  );
}

export function IconAlert() {
  return (
    <svg {...base}>
      <path d="M10 3.2l7 12.3H3z" />
      <path d="M10 8v3.2M10 13.6h.01" />
    </svg>
  );
}

export function IconChevron() {
  return (
    <svg {...base}>
      <path d="M6 8l4 4 4-4" />
    </svg>
  );
}

export function IconCopy() {
  return (
    <svg {...base}>
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
      <path d="M13 7V4.5a1.5 1.5 0 0 0-1.5-1.5h-7A1.5 1.5 0 0 0 3 4.5v7A1.5 1.5 0 0 0 4.5 13H7" />
    </svg>
  );
}

export function IconFileText() {
  return (
    <svg {...base}>
      <path d="M11.5 2.5H6A1.5 1.5 0 0 0 4.5 4v12A1.5 1.5 0 0 0 6 17.5h8a1.5 1.5 0 0 0 1.5-1.5V6.5z" />
      <path d="M11.5 2.5v4h4M7.5 10.5h5M7.5 13.5h5" />
    </svg>
  );
}

export function IconZap() {
  return (
    <svg {...base}>
      <path d="M11.5 2.5L4 11.5h5l-.5 6 7.5-9h-5z" />
    </svg>
  );
}

/** Points right. Flipped for rtl in CSS, so "forward" means forward in either direction. */
export function IconArrow() {
  return (
    <svg {...base}>
      <path d="M4 10h12M11.5 5.5L16 10l-4.5 4.5" />
    </svg>
  );
}

export function IconPencil() {
  return (
    <svg {...base}>
      <path d="M13.4 3.3l3.3 3.3-9 9-4 .7.7-4z" />
      <path d="M11.8 4.9l3.3 3.3" />
    </svg>
  );
}

export function IconEye() {
  return (
    <svg {...base}>
      <path d="M1.8 10S5 4.4 10 4.4 18.2 10 18.2 10 15 15.6 10 15.6 1.8 10 1.8 10z" />
      <circle cx="10" cy="10" r="2.4" />
    </svg>
  );
}

export function IconCrown() {
  return (
    <svg {...base}>
      <path d="M2.6 6.2l3.1 3 4.3-5 4.3 5 3.1-3-1.4 9.1H4z" />
      <path d="M4 15.3h12" />
    </svg>
  );
}

export function IconLock() {
  return (
    <svg {...base}>
      <rect x="4" y="8.6" width="12" height="8.4" rx="2" />
      <path d="M6.9 8.6V6.4a3.1 3.1 0 016.2 0v2.2" />
    </svg>
  );
}
