// The rankings of the Temporada page (the ones of GET /statistics/rankings), drawn as bars.
// Pure (no DOM) so it can be tested. `value` is the number the bar is drawn from, `text` what is written next to it.
import { formatDuration } from './format.js';

const count = (key) => (e) => e[key];
const days = (n) => `${n} ${n === 1 ? 'día' : 'días'}`;
const debtText = (e) => `${formatDuration(e.debt_time)} en ${e.games} ${e.games === 1 ? 'juego' : 'juegos'}`;

/** Every ranking, in the order the page shows them. `api` is the name the API knows it by; `rows: 'games'` is a ranking of games, not of players. */
export const RANKINGS = [
  { id: 'hours', api: 'user_hours', title: 'Tiempo jugado', sub: 'Horas acumuladas en la temporada', value: count('played_time'), text: (e) => formatDuration(e.played_time) },
  { id: 'days', api: 'user_days', title: 'Días jugados', sub: 'Días distintos con alguna sesión', value: count('played_days'), text: (e) => days(e.played_days) },
  { id: 'games', api: 'user_played_games', title: 'Juegos jugados', sub: 'Juegos distintos de la biblioteca', value: count('played_games'), text: count('played_games') },
  { id: 'completed', api: 'user_completed_games', title: 'Juegos completados', sub: 'Terminados en la temporada', value: count('completed_games'), text: count('completed_games') },
  { id: 'ratio', api: 'user_ratio', title: 'Ratio de completado', sub: 'Juegos completados entre jugados', value: count('ratio'), text: (e) => `${Math.round(e.ratio * 100)} %` },
  { id: 'achievements', api: 'achievements', title: 'Logros', sub: 'Desbloqueados en la temporada', value: count('achievements'), text: count('achievements') },
  { id: 'best-streak', api: 'user_best_streak', title: 'Mejor racha', sub: 'Días seguidos jugando', value: count('best_streak'), text: (e) => days(e.best_streak) },
  { id: 'current-streak', api: 'user_current_streak', title: 'Racha actual', sub: 'La que llevan ahora mismo', value: count('current_streak'), text: (e) => days(e.current_streak) },
  { id: 'most-played', api: 'games_most_played', title: 'Juegos más jugados', sub: 'Entre todos', rows: 'games', value: count('played_time'), text: (e) => formatDuration(e.played_time) },
  { id: 'debt', api: 'debt', title: 'Pendiente de la temporada', sub: 'Tiempo que falta para terminar lo empezado (según HLTB)', value: count('debt_time'), text: debtText },
  { id: 'debt-total', api: 'debt_total', title: 'Pendiente total', sub: 'Lo mismo, contando todas las temporadas', value: count('debt_time'), text: debtText },
];

/** What to ask the API for: every ranking of the page in one request (the running season, which is the API's default) and only for the active players. */
export const rankingsPath = () => `/statistics/rankings?only_active=true&ranking=${RANKINGS.map((r) => r.api).join(',')}`;

/** The rows of a ranking from the API's answer (a list of `{ type, data }`); empty when it did not come. */
export const rowsOf = (answer, ranking) => {
  const data = (Array.isArray(answer) ? answer : []).find((r) => r.type === ranking.api)?.data;
  return Array.isArray(data) ? data : [];
};

/** The rows to show: those that count something (a player with nothing is no use in a ranking), in the API's order, at most `limit`. */
export const visibleRows = (rows, ranking, limit) => rows.filter((row) => ranking.value(row) > 0).slice(0, limit);

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
