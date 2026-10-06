// What the wishlist says about a game. Pure, so it can be tested.
import { formatDate, formatPlayers } from './format.js';

/** How long until a game comes out: "Sale hoy", "Mañana", "En 12 días", "En 3 meses", "Sin fecha confirmada", or '' once it is out. */
export function countdown(game) {
  if (!game.release_date) return 'Sin fecha confirmada';
  const days = game.days_until;
  if (days == null) return '';
  if (days === 0) return 'Sale hoy';
  if (days === 1) return 'Mañana';
  if (days <= 60) return `En ${days} días`;
  return `En ${Math.round(days / 30)} meses`;
}

/** The release line of a card: the countdown and the date when there is one. */
export const releaseLine = (game) => [countdown(game), game.release_date && formatDate(game.release_date)].filter(Boolean).join(' · ');

/** "Lo quiere Bea", "Lo quieren Bea y Cai" (nothing when nobody else does). */
export function wantedBy(players) {
  if (!players.length) return '';
  return `${players.length === 1 ? 'Lo quiere' : 'Lo quieren'} ${formatPlayers(players.map((p) => p.name))}`;
}
