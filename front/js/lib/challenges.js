// What the challenges page says about a challenge. Pure, so it can be tested.
import { formatDate, parseDay } from './format.js';

const DAY = 86400000;

/** 25200 -> "7 h", 9000 -> "2,5 h", 0 -> "0 h" (hours with at most a decimal). */
export function hoursLabel(seconds) {
  const hours = Math.round(((seconds || 0) / 3600) * 10) / 10;
  return `${hours.toLocaleString('es-ES')} h`;
}

/** The share of a target reached, 0 to 100 (a target of 0 counts as reached). */
export function percent(seconds, target) {
  if (!target) return 100;
  return Math.min(100, Math.floor(((seconds || 0) / target) * 100));
}

/** "1 oct 2026 – 31 oct 2026" */
export const periodLine = (challenge) => `${formatDate(challenge.starts_on)} – ${formatDate(challenge.ends_on)}`;

/** Whole days from `today` to a "YYYY-MM-DD" day (negative once it is past). */
export function daysUntil(day, today = new Date()) {
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((parseDay(day) - startOfToday) / DAY);
}

/** "Quedan 12 días", "Termina hoy", "Empieza en 3 días", "Terminado". */
export function timeLeft(challenge, today = new Date()) {
  if (challenge.status === 'finished') return 'Terminado';
  if (challenge.status === 'upcoming') {
    const days = daysUntil(challenge.starts_on, today);
    return days === 1 ? 'Empieza mañana' : `Empieza en ${days} días`;
  }
  const days = daysUntil(challenge.ends_on, today);
  if (days <= 0) return 'Termina hoy';
  return days === 1 ? 'Queda 1 día' : `Quedan ${days} días`;
}

/** The next months a group challenge can be launched for, from the running one: [{ value: "2026-10", label: "Octubre 2026" }, ...]. */
export function launchMonths(today = new Date(), count = 4) {
  return Array.from({ length: count }, (_, i) => {
    const date = new Date(today.getFullYear(), today.getMonth() + i, 1);
    const name = date.toLocaleDateString('es-ES', { month: 'long' });
    return { value: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`, label: `${name[0].toUpperCase()}${name.slice(1)} ${date.getFullYear()}` };
  });
}

/** The line a finished challenge gets in a player's history. */
export function resultLine(entry) {
  if (entry.done) return entry.group_done ? 'Cumpliste tu parte y el grupo llegó al total' : 'Cumpliste tu parte';
  return entry.group_done ? 'El grupo llegó al total' : 'No se cumplió';
}
