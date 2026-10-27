// What the game page says about the saga of a game (GET /games/{id}/series). Pure, so it can be tested.
import { formatDuration } from './format.js';

/** The year of a "YYYY-MM-DD" date, or "" when there is none. */
export const releaseYear = (released) => (released ? released.slice(0, 4) : '');

/** Where the viewer stands in one game of the saga: { label, tone } (tone is a pf-tag class: done, live or muted). */
export function standing(game) {
  if (game.mine?.completed) return { label: 'Completado', tone: 'done' };
  if (game.mine) return { label: game.mine.seconds ? `En tu biblioteca · ${formatDuration(game.mine.seconds)}` : 'En tu biblioteca', tone: 'live' };
  return { label: game.game_id ? 'No lo tienes' : 'No está en la biblioteca del grupo', tone: 'muted' };
}

/** "Has completado 2 de 4." and, if there is one, what is next; '' for a saga of nothing. */
export function sagaSummary(games) {
  if (!games.length) return '';
  const done = games.filter((g) => g.mine?.completed).length;
  const next = games.find((g) => g.next);
  return `Has completado ${done} de ${games.length}.${next ? ` Siguiente: ${next.name}.` : ''}`;
}
