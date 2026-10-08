// Hours played day by day, from the "played" events of the activity feed (one per player, game and day).
import { parseDay } from './format.js';

const pad = (n) => String(n).padStart(2, '0');
const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/**
 * The running total of seconds of each player at the end of every day, from the first day somebody played to the last.
 * `events` are the feed's (only the "played" ones of `players` count); `season` (a year) leaves out the other years.
 * Returns null when nobody played. The players come back as they came in: { ...player, values: [seconds per day] }.
 */
export function cumulativeSeries(events, players, season = null) {
  const ids = new Set(players.map((p) => p.user_id));
  const perDay = new Map(); // "user:day" -> seconds
  let first = null;
  let last = null;
  for (const e of events) {
    if (e.type !== 'played' || !ids.has(e.user_id) || (season !== null && !e.day.startsWith(`${season}-`))) continue;
    perDay.set(`${e.user_id}:${e.day}`, (perDay.get(`${e.user_id}:${e.day}`) ?? 0) + e.seconds);
    if (first === null || e.day < first) first = e.day;
    if (last === null || e.day > last) last = e.day;
  }
  if (first === null) return null;
  const days = [];
  for (const d = parseDay(first); isoDay(d) <= last; d.setDate(d.getDate() + 1)) days.push(isoDay(d));
  const series = players.map((p) => {
    let total = 0;
    return { ...p, values: days.map((day) => (total += perDay.get(`${p.user_id}:${day}`) ?? 0)) };
  });
  return { days, series };
}

/** The top of the vertical axis and its ticks, in whole hours: 3600 s -> { top: 4, ticks: [0, 1, 2, 3, 4] }. */
export function hourAxis(maxSeconds) {
  const step = Math.max(1, Math.ceil(maxSeconds / 3600 / 4));
  return { top: step * 4, ticks: [0, 1, 2, 3, 4].map((i) => i * step) };
}
