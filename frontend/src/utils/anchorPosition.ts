export interface AnchoredPosition {
  left: number;
  top: number;
  maxHeight: number;
}

/**
 * Places a floating panel against a trigger element, always fully inside the viewport.
 *
 * Panels here are portaled to <body> with `position: fixed` so they escape the grid's
 * `overflow: auto`. The panel is put below the trigger when it fits, above when that
 * side has room, and pinned to the top edge when neither does - never anchored so far
 * off that its buttons land outside the viewport.
 */
export function anchoredPosition(
  rect: DOMRect,
  opts: { width: number; preferredHeight: number; gap?: number; edge?: number }
): AnchoredPosition {
  const gap = opts.gap ?? 4;
  const edge = opts.edge ?? 8;

  const left = Math.min(Math.max(rect.left, edge), window.innerWidth - opts.width - edge);
  const maxHeight = Math.min(opts.preferredHeight, window.innerHeight - 2 * edge);

  const spaceBelow = window.innerHeight - rect.bottom - gap - edge;
  const spaceAbove = rect.top - gap - edge;

  let top: number;
  if (spaceBelow >= maxHeight) top = rect.bottom + gap;
  else if (spaceAbove >= maxHeight) top = rect.top - gap - maxHeight;
  else top = edge;

  return { left, top, maxHeight };
}
