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

/** Splits the list for one viewer: the others still playing, the others whose timer is stale (dimmed), the
 * viewer's own running timer (null if none or stale) and whether there is one. */
export function summarize(list, myId) {
  const others = list.filter((p) => p.user_id !== myId);
  const mine = list.find((p) => p.user_id === myId && !p.stale) ?? null;
  return {
    fresh: others.filter((p) => !p.stale),
    stale: others.filter((p) => p.stale),
    mine,
    meActive: mine !== null,
  };
}

/** The players with a running timer on the same game, whatever the platform (that says nothing about playing
 * together: each one may be at home with a single player game). Groups come in the order their game first
 * appears; `shared` is true when there is more than one player in it. */
export function groupByGame(players) {
  const groups = new Map();
  for (const p of players) {
    if (!groups.has(p.game_id)) groups.set(p.game_id, { game_id: p.game_id, game_name: p.game_name, players: [] });
    groups.get(p.game_id).players.push(p);
  }
  return [...groups.values()].map((g) => ({ ...g, shared: g.players.length > 1 }));
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
