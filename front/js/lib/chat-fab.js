// Where the chat button rests: the player drags it, and on release it sticks to the nearest side edge at the height
// they left it. Pure functions; js/ui/chat.js does the pointer handling and css/chat.css the drawing.

export const FAB_SIZE = 56;
export const FAB_MARGIN = 16;
export const DRAG_THRESHOLD = 6; // px of movement before a press becomes a drag (below it, it is a tap)

/** The side and the distance from the bottom edge at which the button rests, given where it was dropped. */
export function snapFab({ left, top, width, height, minBottom }) {
  const side = left + FAB_SIZE / 2 < width / 2 ? 'left' : 'right';
  const maxBottom = Math.max(minBottom, height - FAB_SIZE - FAB_MARGIN);
  const bottom = Math.min(Math.max(height - (top + FAB_SIZE), minBottom), maxBottom);
  return { side, bottom: Math.round(bottom) };
}

/** What was saved, or null when it is missing or not a valid position (storage can hold anything). */
export function parseFabPosition(raw) {
  try {
    const p = JSON.parse(raw);
    if ((p?.side === 'left' || p?.side === 'right') && Number.isFinite(p.bottom) && p.bottom >= 0 && p.bottom < 10000) {
      return { side: p.side, bottom: Math.round(p.bottom) };
    }
  } catch { /* not JSON */ }
  return null;
}
