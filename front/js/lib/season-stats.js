// The rankings of the Temporada page (the ones of GET /statistics/rankings), drawn as bars.
// Pure (no DOM) so it can be tested. `value` is the number the bar is drawn from, `text` what is written next to it.
import { DAY_RULE } from './day-rule.js';
import { formatDuration } from './format.js';
import { perHour } from './money.js';
import { FIRST, current } from './seasons.js';

const count = (key) => (e) => e[key];
const days = (n) => `${n} ${n === 1 ? 'día' : 'días'}`;

/** The pill that adds every season together: it is the API's `season=0` (no real season is 0). */
export const TOTAL = 0;

/** Every ranking, in the order the page shows them. `api` is the name the API knows it by; `total: true` one that only exists in the Total; `order: 'asc'` one where the lowest value is the best; `then` the rankings that break a tie, in order (see rowsOf); `info` the text of an "i" beside the title, when the figure needs explaining; `view` how it is drawn (podium, bars, tiles, rings or covers); `rows: 'games'` is a ranking of games, not of players. */
export const RANKINGS = [
  { id: 'hours', view: 'podium', then: ['days', 'games'], api: 'user_hours', title: 'Tiempo jugado', value: count('played_time'), text: (e) => formatDuration(e.played_time) },
  { id: 'days', view: 'podium', then: ['hours', 'games'], api: 'user_days', info: DAY_RULE, title: 'Días jugados', value: count('played_days'), text: (e) => days(e.played_days) },
  { id: 'games', view: 'podium', then: ['hours', 'days'], unit: 'juegos', api: 'user_played_games', title: 'Juegos jugados', value: count('played_games'), text: count('played_games') },
  { id: 'completed', view: 'podium', then: ['ratio', 'hours'], api: 'user_completed_games', title: 'Juegos completados', value: count('completed_games'), text: count('completed_games') },
  { id: 'ratio', view: 'podium', then: ['completed', 'hours'], api: 'user_ratio', title: 'Ratio de completado', value: count('ratio'), text: (e) => `${Math.round(e.ratio * 100)} %` },
  { id: 'achievements', view: 'podium', then: ['hours', 'days'], api: 'achievements', title: 'Logros', value: count('achievements'), text: count('achievements') },
  { id: 'best-streak', view: 'podium', then: ['days', 'hours'], unit: 'días', icon: '🏆', api: 'user_best_streak', info: DAY_RULE, title: 'Mejor racha', value: count('best_streak'), text: (e) => days(e.best_streak) },
  { id: 'current-streak', view: 'podium', then: ['best-streak', 'days', 'hours'], unit: 'días', icon: '🔥', api: 'user_current_streak', info: DAY_RULE, title: 'Racha actual', value: count('current_streak'), text: (e) => days(e.current_streak) },
  { id: 'most-played', view: 'podium', api: 'games_most_played', title: 'Juegos más jugados', rows: 'games', value: count('played_time'), text: (e) => formatDuration(e.played_time) },
  // The cost per hour of the group's games (never a player, never a price): it comes from what everybody paid over all their
  // hours, not from a season, so these two cards only exist in the Total. The cheapest has the shortest bar the lowest value.
  { id: 'cheapest', view: 'podium', api: 'games_value_cheapest', title: 'Juegos más baratos por hora', rows: 'games', total: true, order: 'asc', value: count('per_hour_cents'), text: (e) => `${perHour(e.per_hour_cents)} · ${e.contributors} jug.` },
  { id: 'priciest', view: 'podium', api: 'games_value_priciest', title: 'Juegos más caros por hora', rows: 'games', total: true, value: count('per_hour_cents'), text: (e) => `${perHour(e.per_hour_cents)} · ${e.contributors} jug.` },
];

/** The rankings a season has: a streak that is still running only makes sense for the running season. */
export const rankingsOf = (season = current()) => RANKINGS.filter((r) => (r.id !== 'current-streak' || season === current()) && (!r.total || season === TOTAL));

/** What to ask the API for: every ranking of the season (the running one by default) in one request. The running season is
 * only for the active players; an older one is for everybody, and `participantsOf` leaves out those who took no part in it. */
export const rankingsPath = (season = current()) => `/statistics/rankings?only_active=${season === current()}&season=${season}&ranking=${rankingsOf(season).map((r) => r.api).join(',')}`;

/** Does the address ask for the hall of fame (`#/season/fame`)? */
export const isFameHash = (hash) => /^#\/season\/fame\/?$/.test(hash ?? '');

/** The season an address asks for (`#/season/2025`), or TOTAL (`#/season/total`); the running one when it names none or a season that cannot exist. */
export function seasonFromHash(hash, now = new Date()) {
  if (/^#\/season\/total\/?$/.test(hash ?? '')) return TOTAL;
  const match = /^#\/season\/(\d{4})\/?$/.exec(hash ?? '');
  const year = match ? Number(match[1]) : null;
  return year !== null && year >= FIRST && year <= current(now) ? year : current(now);
}

const rowsOfType = (answer, ranking) => {
  const data = (Array.isArray(answer) ? answer : []).find((r) => r.type === ranking.api)?.data;
  return Array.isArray(data) ? data : [];
};

/** {user id: value} of another ranking of the same answer, to break ties with it (a player missing from it has 0). */
const valuesOf = (answer, id) => {
  const ranking = RANKINGS.find((r) => r.id === id);
  return new Map(rowsOfType(answer, ranking).map((row) => [row.user_id, ranking.value(row)]));
};

/** The rows of a ranking from the API's answer (a list of `{ type, data }`), best first; empty when it did not come. With
 * `players` (a set of ids, see participantsOf) a ranking of players keeps only those.
 *
 * Nobody shares a place: a tie in the value is broken by the rankings in `ranking.then` (the one that says most about
 * the same effort first, the larger value winning), and what is still tied goes in alphabetical order. The games break it with the day they were last played. */
export const rowsOf = (answer, ranking, players = null) => {
  let rows = rowsOfType(answer, ranking);
  if (players && ranking.rows !== 'games') rows = rows.filter((row) => players.has(row.user_id));
  const breakers = ranking.rows === 'games' ? [] : (ranking.then ?? []).map((id) => valuesOf(answer, id));
  // games with the same value: the one more players contribute to, then the one played later (the start of its latest session)
  const later = (a, b) => (ranking.rows === 'games'
    ? (b.contributors ?? 0) - (a.contributors ?? 0) || String(b.last_played ?? '').localeCompare(String(a.last_played ?? ''))
    : 0);
  const sign = ranking.order === 'asc' ? -1 : 1;
  return [...rows].sort((a, b) => sign * (ranking.value(b) - ranking.value(a))
    || later(a, b)
    || breakers.reduce((diff, values) => diff || (values.get(b.user_id) ?? 0) - (values.get(a.user_id) ?? 0), 0)
    || String(a.name).localeCompare(String(b.name), 'es', { sensitivity: 'base' }));
};

/** The ids of the players who took part in a season: those with something in any ranking of players (the API lists everybody,
 * with zeros). Whether they are active today does not matter. */
export function participantsOf(answer, rankings) {
  const ids = new Set();
  for (const ranking of rankings.filter((r) => r.rows !== 'games')) {
    for (const row of rowsOf(answer, ranking)) if (ranking.value(row) > 0) ids.add(row.user_id);
  }
  return ids;
}

/** How far each bar goes, 0 to 100: the longest is full and the rest go in proportion. */
export function barWidths(rows, ranking) {
  if (ranking.order === 'asc') { // the lowest is the best and has the full bar
    const low = Math.min(...rows.map((row) => ranking.value(row)));
    return rows.map((row) => (ranking.value(row) > 0 ? Math.round((low / ranking.value(row)) * 100) : 100));
  }
  const top = Math.max(0, ...rows.map((row) => ranking.value(row)));
  return rows.map((row) => (top > 0 ? Math.round((ranking.value(row) / top) * 100) : 0));
}

/** The place of each row (1, 2, 3...): rowsOf has already broken every tie, so nobody shares one. */
export const positions = (rows) => rows.map((_, i) => i + 1);

/** The first three rows laid out as a podium: second, first, third (fewer when there are fewer rows). */
export const podiumOrder = (rows) => [1, 0, 2].filter((i) => i < Math.min(rows.length, 3));

/** The part of a ring a ratio (0 to 1) fills, as a percentage of the circle. */
export const ringPercent = (ratio) => Math.max(0, Math.min(100, Math.round(ratio * 100)));
