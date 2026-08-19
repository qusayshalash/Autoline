/** Toolbar / pager glyphs for the spreadsheet view. Inline SVG so they inherit
 *  currentColor and need no icon dependency. */

const base = {
  width: 14,
  height: 14,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function IconReset() {
  return (
    <svg {...base}>
      <path d="M2.5 8a5.5 5.5 0 1 0 1.7-4" />
      <path d="M2 2.5V6h3.5" />
    </svg>
  );
}

export function IconColumns() {
  return (
    <svg {...base}>
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
      <path d="M6 2.5v11M10 2.5v11" />
    </svg>
  );
}

export function IconFilter() {
  return (
    <svg {...base}>
      <path d="M2.5 3.5h11l-4.2 5v4l-2.6 1.2V8.5z" />
    </svg>
  );
}

export function IconSort() {
  return (
    <svg {...base}>
      <path d="M4 3v10M4 13l-2-2M4 13l2-2" />
      <path d="M9 4.5h5M9 8h4M9 11.5h3" />
    </svg>
  );
}

export function IconStats() {
  return (
    <svg {...base}>
      <path d="M3 13V8M8 13V3M13 13v-3" />
    </svg>
  );
}

export function IconDownload() {
  return (
    <svg {...base}>
      <path d="M8 2.5v7.5M8 10l-3-3M8 10l3-3" />
      <path d="M2.5 12.5h11" />
    </svg>
  );
}

export function IconClock() {
  return (
    <svg {...base}>
      <circle cx="8" cy="8" r="5.8" />
      <path d="M8 4.6V8l2.4 1.6" />
    </svg>
  );
}

export function IconRecords() {
  return (
    <svg {...base}>
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      <path d="M2 6.4h12M2 9.7h12M5.8 3v10" />
    </svg>
  );
}

export function IconTrash() {
  return (
    <svg {...base}>
      <path d="M2.5 4.5h11M6 4.5V3h4v1.5M4 4.5l.6 8.2a1 1 0 0 0 1 .8h4.8a1 1 0 0 0 1-.8L12 4.5" />
      <path d="M6.6 7v4M9.4 7v4" />
    </svg>
  );
}

export function IconPlusCircle() {
  return (
    <svg {...base}>
      <circle cx="8" cy="8" r="5.8" />
      <path d="M8 5.4v5.2M5.4 8h5.2" />
    </svg>
  );
}

export function IconClose() {
  return (
    <svg {...base}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}

export function IconCheck() {
  return (
    <svg {...base}>
      <circle cx="8" cy="8" r="5.8" />
      <path d="m5.3 8.1 1.7 1.8 3.8-4" />
    </svg>
  );
}

export function IconChevronLeft() {
  return (
    <svg {...base}>
      <path d="M10 3l-5 5 5 5" />
    </svg>
  );
}

export function IconChevronRight() {
  return (
    <svg {...base}>
      <path d="M6 3l5 5-5 5" />
    </svg>
  );
}

export function IconFirst() {
  return (
    <svg {...base}>
      <path d="M11 3L6 8l5 5M4 3v10" />
    </svg>
  );
}

export function IconLast() {
  return (
    <svg {...base}>
      <path d="M5 3l5 5-5 5M12 3v10" />
    </svg>
  );
}
