// Who is playing right now (GET /timers/now-playing). One shared state for the whole app: it is
// refreshed every INTERVAL_MS while the app is visible, when it comes back to the foreground and
// whenever a page asks (every screen change), and whoever draws it subscribes to the changes.
import { api } from './api.js';

export const INTERVAL_MS = 45_000;

let players = [];
let timer = null;
let running = false;
const listeners = new Set();

export const current = () => players;

/** `fn(players)` runs after every refresh; returns the function that unsubscribes. */
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Splits the list for one viewer: the others still playing, the others whose timer is stale (dimmed), and
 * whether the viewer's own timer is running. */
export function summarize(list, myId) {
  const others = list.filter((p) => p.user_id !== myId);
  return {
    fresh: others.filter((p) => !p.stale),
    stale: others.filter((p) => p.stale),
    meActive: list.some((p) => p.user_id === myId && !p.stale),
  };
}

export async function refresh() {
  let list;
  try {
    list = await api('/timers/now-playing');
  } catch {
    return; // a failed refresh keeps what is on screen
  }
  if (!Array.isArray(list)) return;
  players = list;
  listeners.forEach((fn) => fn(players));
}

const onVisibility = () => { if (!document.hidden) refresh(); };

export function startPresence() {
  if (running) return;
  running = true;
  timer = setInterval(() => { if (!document.hidden) refresh(); }, INTERVAL_MS);
  document.addEventListener('visibilitychange', onVisibility);
  refresh();
}

export function stopPresence() {
  running = false;
  clearInterval(timer);
  document.removeEventListener('visibilitychange', onVisibility);
  players = [];
}
