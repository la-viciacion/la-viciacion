// Months and days of the release calendar. Pure, so it can be tested. A month is "YYYY-MM", a day "YYYY-MM-DD".
import { formatPlayers } from './format.js';

const pad = (n) => String(n).padStart(2, '0');

/** The month of a Date, "2026-10". */
export const monthOf = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;

/** "2026-12" moved by `by` months: "2027-01" for 1. */
export function shiftMonth(month, by) {
  const [year, number] = month.split('-').map(Number);
  const index = year * 12 + (number - 1) + by;
  return `${Math.floor(index / 12)}-${pad((index % 12) + 1)}`;
}

/** "Octubre 2026" */
export function monthLabel(month) {
  const [year, number] = month.split('-').map(Number);
  const name = new Date(year, number - 1, 1).toLocaleDateString('es-ES', { month: 'long' });
  return `${name[0].toUpperCase()}${name.slice(1)} ${year}`;
}

/** The weeks of the month, Monday first: arrays of 7 cells, each a day "YYYY-MM-DD" or null outside the month. */
export function monthWeeks(month) {
  const [year, number] = month.split('-').map(Number);
  const lead = (new Date(year, number - 1, 1).getDay() + 6) % 7; // Monday = 0
  const days = new Date(year, number, 0).getDate();
  const cells = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => `${month}-${pad(i + 1)}`)];
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, week) => cells.slice(week * 7, week * 7 + 7));
}

/** The releases of the month grouped by day: { "2026-10-23": [game, ...] }. */
export function byDay(releases) {
  const days = {};
  for (const game of releases) (days[game.release_date] ||= []).push(game);
  return days;
}

/** "Lo quieren Ana, tú y Bea" (the viewer is "tú"; nothing when nobody wants it). */
export function waiting(players) {
  if (!players.length) return '';
  const names = players.map((p) => (p.is_me ? 'tú' : p.name));
  return `${players.length === 1 ? 'Lo quiere' : 'Lo quieren'} ${formatPlayers(names)}`;
}
