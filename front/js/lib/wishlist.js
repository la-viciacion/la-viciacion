// What the wishlist says about a game. Pure, so it can be tested.
import { formatDate, formatPlayers } from './format.js';

/** How long until a game comes out: "Ya ha salido", "Mañana", "En 12 días", "En 3 meses", or "Sin fecha confirmada". */
export function countdown(game) {
  if (!game.release_date) return 'Sin fecha confirmada';
  const days = game.days_until;
  if (days == null) return 'Ya ha salido'; // the API sends no days for a date that is today or past
  if (days === 1) return 'Mañana';
  if (days <= 60) return `En ${days} días`;
  return `En ${Math.round(days / 30)} meses`;
}

/** The release line of a card: the countdown and the date when there is one. */
export const releaseLine = (game) => (game.release_date ? `${countdown(game)} · ${formatDate(game.release_date)}` : countdown(game));

/** "Lo quiere Bea", "Lo quieren Bea y Cai" (nothing when nobody else does). */
export function wantedBy(players) {
  if (!players.length) return '';
  return `${players.length === 1 ? 'Lo quiere' : 'Lo quieren'} ${formatPlayers(players.map((p) => p.name))}`;
}
