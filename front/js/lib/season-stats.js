// The rankings of the Temporada page (the ones of GET /statistics/rankings), drawn as bars.
// Pure (no DOM) so it can be tested. `value` is the number the bar is drawn from, `text` what is written next to it.
import { formatDuration } from './format.js';
import { FIRST, current } from './seasons.js';

const count = (key) => (e) => e[key];
const days = (n) => `${n} ${n === 1 ? 'día' : 'días'}`;

/** Every ranking, in the order the page shows them. `api` is the name the API knows it by; `view` how it is drawn (podium, bars, tiles, rings or covers); `rows: 'games'` is a ranking of games, not of players. */
export const RANKINGS = [
  { id: 'hours', view: 'podium', api: 'user_hours', title: 'Tiempo jugado', value: count('played_time'), text: (e) => formatDuration(e.played_time) },
  { id: 'days', view: 'podium', api: 'user_days', title: 'Días jugados', value: count('played_days'), text: (e) => days(e.played_days) },
  { id: 'games', view: 'podium', unit: 'juegos', api: 'user_played_games', title: 'Juegos jugados', value: count('played_games'), text: count('played_games') },
  { id: 'completed', view: 'podium', api: 'user_completed_games', title: 'Juegos completados', value: count('completed_games'), text: count('completed_games') },
  { id: 'ratio', view: 'podium', api: 'user_ratio', title: 'Ratio de completado', value: count('ratio'), text: (e) => `${Math.round(e.ratio * 100)} %` },
  { id: 'achievements', view: 'podium', api: 'achievements', title: 'Logros', value: count('achievements'), text: count('achievements') },
  { id: 'best-streak', view: 'podium', unit: 'días', icon: '🏆', api: 'user_best_streak', title: 'Mejor racha', value: count('best_streak'), text: (e) => days(e.best_streak) },
  { id: 'current-streak', view: 'podium', unit: 'días', icon: '🔥', api: 'user_current_streak', title: 'Racha actual', value: count('current_streak'), text: (e) => days(e.current_streak) },
  { id: 'most-played', view: 'podium', api: 'games_most_played', title: 'Juegos más jugados', rows: 'games', value: count('played_time'), text: (e) => formatDuration(e.played_time) },
];

/** The rankings a season has: a streak that is still running only makes sense for the running season. */
export const rankingsOf = (season = current()) => RANKINGS.filter((r) => r.id !== 'current-streak' || season === current());

/** What to ask the API for: every ranking of the season (the running one by default) in one request, only for the active players. */
export const rankingsPath = (season = current()) => `/statistics/rankings?only_active=true&season=${season}&ranking=${rankingsOf(season).map((r) => r.api).join(',')}`;

/** The season an address asks for (`#/season/2025`); the running one when it names none or a season that cannot exist. */
export function seasonFromHash(hash, now = new Date()) {
  const match = /^#\/season\/(\d{4})\/?$/.exec(hash ?? '');
  const year = match ? Number(match[1]) : null;
  return year !== null && year >= FIRST && year <= current(now) ? year : current(now);
}

/** The rows of a ranking from the API's answer (a list of `{ type, data }`); empty when it did not come. */
export const rowsOf = (answer, ranking) => {
  const data = (Array.isArray(answer) ? answer : []).find((r) => r.type === ranking.api)?.data;
  return Array.isArray(data) ? data : [];
};

/** How far each bar goes, 0 to 100: the longest is full and the rest go in proportion. */
export function barWidths(rows, ranking) {
  const top = Math.max(0, ...rows.map((row) => ranking.value(row)));
  return rows.map((row) => (top > 0 ? Math.round((ranking.value(row) / top) * 100) : 0));
}

/** The place of each row (1, 2, 2, 4...): those with the same value share it, as on a podium. */
export function positions(rows, ranking) {
  const out = [];
  rows.forEach((row, i) => out.push(i > 0 && ranking.value(rows[i - 1]) === ranking.value(row) ? out[i - 1] : i + 1));
  return out;
}

/** The first three rows laid out as a podium: second, first, third (fewer when there are fewer rows). */
export const podiumOrder = (rows) => [1, 0, 2].filter((i) => i < Math.min(rows.length, 3));

/** The part of a ring a ratio (0 to 1) fills, as a percentage of the circle. */
export const ringPercent = (ratio) => Math.max(0, Math.min(100, Math.round(ratio * 100)));
