// The hall of fame of the Temporada page (#/season/fame): the champions of each closed season, from
// GET /statistics/hall-of-fame. Pure (no DOM) so it can be tested.
import { formatDuration } from './format.js';

/** What stands in the address (#/season/fame) and in the pill of the page. */
export const FAME = 'fame';

const days = (n) => `${n} ${n === 1 ? 'día' : 'días'}`;

/** The categories a season has a champion in, in the order the page shows them; `text` writes a figure. */
export const CATEGORIES = [
  { id: 'hours', title: 'Tiempo jugado', text: formatDuration },
  { id: 'days', title: 'Días jugados', text: days },
  { id: 'games', title: 'Juegos jugados', text: String },
  { id: 'completed', title: 'Juegos completados', text: String },
  { id: 'achievements', title: 'Logros', text: String },
  { id: 'streak', title: 'Mejor racha', text: days },
];

/** "1 título", "3 títulos". */
export const titlesText = (n) => `${n} ${n === 1 ? 'título' : 'títulos'}`;

/** The seasons of the answer that have at least a champion (a season in which nobody did anything says nothing). */
export const seasonsWithChampions = (answer) =>
  (Array.isArray(answer?.seasons) ? answer.seasons : []).filter((entry) => Object.values(entry.champions ?? {}).some((winners) => winners?.length));

/** The players with titles, most first (the API sends them sorted; a missing answer is nobody). */
export const titleRanking = (answer) => (Array.isArray(answer?.titles) ? answer.titles : []);
