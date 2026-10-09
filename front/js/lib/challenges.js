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

/** A part of a challenge is counted in games ("complete") or in seconds ("play", the group's ones). */
export const isCount = (part) => 'target_count' in part;
export const partValue = (part) => (isCount(part) ? part.count : part.seconds);
export const partTarget = (part) => (isCount(part) ? part.target_count : part.target_seconds);

/** "3 / 5 h" or "0 / 1 juego" */
export function amountLabel(part) {
  if (isCount(part)) return `${part.count} / ${part.target_count} ${part.target_count === 1 ? 'juego' : 'juegos'}`;
  return `${hoursLabel(part.seconds)} / ${hoursLabel(part.target_seconds)}`;
}

/** What a challenge asks, in a line. */
export function summaryLine(challenge) {
  const p = challenge.params;
  if (challenge.kind === 'game_of_month') {
    return `${challenge.label} · mínimo ${hoursLabel(p.min_hours_each * 3600)} cada uno y ${hoursLabel(p.min_hours_total * 3600)} entre todos`;
  }
  if (challenge.kind === 'new_genre') {
    const what = p.mode === 'play' ? `jugar ${hoursLabel(p.hours * 3600)} a` : 'completar';
    return `${challenge.label} · ${what} un juego de ${p.genre} que no tuvieras antes`;
  }
  return challenge.label;
}

const ORDER = { active: 0, upcoming: 1, finished: 2 };
const FINISHED_SHOWN = 5;

/** The page's blocks: the group's challenges, the viewer's own and the other players', each with the running ones
 * first and only the latest finished ones. [{ key, title, list, empty }] (the others' block only when there is one). */
export function blocks(challenges, meId) {
  const sorted = (list) => [...list].sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const cut = (list) => [...sorted(list).filter((c) => c.status !== 'finished'), ...sorted(list).filter((c) => c.status === 'finished').slice(0, FINISHED_SHOWN)];
  const group = challenges.filter((c) => c.scope === 'group');
  const mine = challenges.filter((c) => c.scope === 'user' && c.owner?.id === meId);
  const others = challenges.filter((c) => c.scope === 'user' && c.owner?.id !== meId);
  return [
    { key: 'group', title: 'Del grupo', list: cut(group), empty: 'No hay ningún reto del grupo.' },
    { key: 'mine', title: 'Tuyos', list: cut(mine), empty: 'No tienes ningún reto. Lanza uno con «Nuevo reto».' },
    ...(others.length ? [{ key: 'others', title: 'De otros jugadores', list: cut(others), empty: '' }] : []),
  ];
}

/** How long a personal challenge lasts, to choose from. */
export const DURATIONS = [['week', 'Una semana'], ['month', 'Un mes'], ['quarter', 'Tres meses']];

/** The line a finished challenge gets in a player's history. */
export function resultLine(entry) {
  if (entry.scope === 'user') return entry.done ? 'Lo conseguiste' : 'No se cumplió';
  if (entry.done) return entry.group_done ? 'Cumpliste tu parte y el grupo llegó al total' : 'Cumpliste tu parte';
  return entry.group_done ? 'El grupo llegó al total' : 'No se cumplió';
}
