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

export function IconChart() {
  return (
    <svg {...base}>
      <path d="M3 16.5h14" />
      <rect x="4" y="9" width="3" height="6" rx="1" />
      <rect x="8.5" y="5.5" width="3" height="9.5" rx="1" />
      <rect x="13" y="11.5" width="3" height="3.5" rx="1" />
    </svg>
  );
}

export function IconDonut() {
  return (
    <svg {...base}>
      <circle cx="10" cy="10" r="7" />
      <circle cx="10" cy="10" r="3" />
      <path d="M10 3v4" />
    </svg>
  );
}

export function IconFilter() {
  return (
    <svg {...base}>
      <path d="M3 5h14l-5.4 6.2v4.3l-3.2 1.8v-6.1z" />
    </svg>
  );
}

export function IconReset() {
  return (
    <svg {...base}>
      <path d="M4 10a6 6 0 1 0 1.8-4.3" />
      <path d="M3.2 3.5v3.4h3.4" />
    </svg>
  );
}

export function IconClose() {
  return (
    <svg {...base}>
      <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" />
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

export function IconDownload() {
  return (
    <svg {...base}>
      <path d="M10 3.5v8.5M6.5 9l3.5 3 3.5-3" />
      <path d="M3.5 15.5h13" />
    </svg>
  );
}

export function IconImage() {
  return (
    <svg {...base}>
      <rect x="3" y="4" width="14" height="12" rx="2" />
      <circle cx="7.5" cy="8" r="1.3" />
      <path d="M3.4 13.5l3.8-3.4 3 2.6 2.5-2.1 3.9 3.4" />
    </svg>
  );
}

export function IconBack() {
  return (
    <svg {...base}>
      <path d="M8 4.5L2.5 10 8 15.5" />
      <path d="M2.5 10h15" />
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

export function IconFile() {
  return (
    <svg {...base}>
      <path d="M11 2.8H6a1.5 1.5 0 0 0-1.5 1.5v11.4A1.5 1.5 0 0 0 6 17.2h8a1.5 1.5 0 0 0 1.5-1.5V7.3z" />
      <path d="M11 2.8v4.5h4.5" />
    </svg>
  );
}

export function IconClock() {
  return (
    <svg {...base}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6v4.2l2.6 1.6" />
    </svg>
  );
}

export function IconSpark() {
  return (
    <svg {...base}>
      <path d="M10 2.8l1.7 4.2 4.5.3-3.5 2.9 1.1 4.4L10 12.2 6.2 14.6l1.1-4.4L3.8 7.3l4.5-.3z" />
    </svg>
  );
}

export function IconTable() {
  return (
    <svg {...base}>
      <rect x="3" y="4" width="14" height="12" rx="1.6" />
      <path d="M3 8h14M8 8v8" />
    </svg>
  );
}

export function IconSearch() {
  return (
    <svg {...base}>
      <circle cx="9" cy="9" r="5.2" />
      <path d="M12.8 12.8L17 17" />
    </svg>
  );
}
