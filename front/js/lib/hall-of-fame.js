// The hall of fame of the Temporada page (#/season/fame): the champions of each closed season, from
// GET /statistics/hall-of-fame. Pure (no DOM) so it can be tested.
import { formatDuration } from './format.js';

/** What stands in the address (#/season/fame) and in the pill of the page. */
export const FAME = 'fame';

const days = (n) => `${n} ${n === 1 ? 'día' : 'días'}`;

/** The categories a season has a champion in, in the order the page shows them; `short` heads a column and `text` writes a figure. */
export const CATEGORIES = [
  { id: 'hours', title: 'Tiempo jugado', short: 'Tiempo', text: formatDuration },
  { id: 'days', title: 'Días jugados', short: 'Días', text: days },
  { id: 'games', title: 'Juegos jugados', short: 'Jugados', text: String },
  { id: 'completed', title: 'Juegos completados', short: 'Completados', text: String },
  { id: 'achievements', title: 'Logros', short: 'Logros', text: String },
  { id: 'streak', title: 'Mejor racha', short: 'Racha', text: days },
];

/** The seasons of the answer that have at least a champion (a season in which nobody did anything says nothing). */
export const seasonsWithChampions = (answer) =>
  (Array.isArray(answer?.seasons) ? answer.seasons : []).filter((entry) => Object.values(entry.champions ?? {}).some((winners) => winners?.length));

/** The players with titles, most first (the API sends them sorted; a missing answer is nobody). */
export const titleRanking = (answer) => (Array.isArray(answer?.titles) ? answer.titles : []);

/** How many colours tell the players apart (`hf-h0` to `hf-h7` in season.css). */
export const HUES = 8;

/** A colour for each player with titles, by their place in the ranking of titles (so the ones that matter most never share
 * one; past the eighth they start over). Returns a Map of user id to a number from 0 to HUES - 1. */
export const playerHues = (answer) => new Map(titleRanking(answer).map((player, i) => [player.user_id, i % HUES]));

/** The player (or players, on a tie) who won most categories of a season, with how many, and how many categories had a champion. */
export function grandChampions(entry) {
  const wins = new Map();
  let decided = 0;
  for (const winners of Object.values(entry.champions ?? {})) {
    if (!winners?.length) continue;
    decided += 1;
    for (const winner of winners) wins.set(winner.user_id, { user_id: winner.user_id, name: winner.name, wins: (wins.get(winner.user_id)?.wins ?? 0) + 1 });
  }
  const top = Math.max(0, ...[...wins.values()].map((w) => w.wins));
  return { winners: [...wins.values()].filter((w) => w.wins === top && top > 0), wins: top, decided };
}
