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

/** A part of a challenge is counted in games, in a share of the debt paid or in seconds. */
export const isCount = (part) => 'target_count' in part;
export const isPercent = (part) => 'target_percent' in part;
export const partValue = (part) => (isCount(part) ? part.count : isPercent(part) ? part.percent : part.seconds);
export const partTarget = (part) => (isCount(part) ? part.target_count : isPercent(part) ? part.target_percent : part.target_seconds);

const number = (n) => n.toLocaleString('es-ES');

/** "3 / 5 h", "0 / 1 juego" or "12,5 % / 25 %" */
export function amountLabel(part) {
  if (isCount(part)) return `${part.count} / ${part.target_count} ${part.target_count === 1 ? 'juego' : 'juegos'}`;
  if (isPercent(part)) return `${number(part.percent)} % / ${number(part.target_percent)} %`;
  return `${hoursLabel(part.seconds)} / ${hoursLabel(part.target_seconds)}`;
}

/** What a "reduce the debt" goal means for the player, said before they accept it. `debt` is GET /challenges/debt
 * ({ seconds, games, open_games }): a percentage becomes the hours it is about, a number of games is checked against the
 * ones they have open. */
export function debtPreview(mode, value, debt) {
  if (!debt.open_games) return 'No tienes juegos empezados y sin terminar: no hay deuda que saldar.';
  if (mode === 'games') {
    const open = debt.open_games === 1 ? '1 juego sin terminar' : `${debt.open_games} juegos sin terminar`;
    return value > debt.open_games ? `Solo tienes ${open}.` : `Tienes ${open}; cerrar ${value} es completar ${value === 1 ? 'uno' : value}.`;
  }
  if (!debt.seconds) return 'Tus juegos empezados ya pasan de su tiempo medio: un porcentaje no tiene deuda que saldar. Prueba a cerrar juegos.';
  const left = `${hoursLabel(debt.seconds)} en ${debt.games === 1 ? '1 juego' : `${debt.games} juegos`}`;
  if (!(value >= 1 && value <= 100)) return `Tu deuda ahora: ${left}. Elige entre 1 y 100 %.`;
  return `El ${number(value)} % de tu deuda son unas ${hoursLabel((debt.seconds * value) / 100)} (tu deuda ahora: ${left}).`;
}

/** What a challenge asks, in a line. */
export function summaryLine(challenge) {
  const p = challenge.params;
  if (challenge.kind === 'game_of_month') {
    return `${challenge.label} · mínimo ${hoursLabel(p.min_hours_each * 3600)} cada uno y ${hoursLabel(p.min_hours_total * 3600)} entre todos`;
  }
  if (challenge.kind === 'themed') {
    if (p.mode === 'play') {
      const total = p.min_hours_total ? ` y ${hoursLabel(p.min_hours_total * 3600)} entre todos` : '';
      return `${challenge.label} · jugar ${hoursLabel(p.min_hours_each * 3600)} cada uno a juegos de ${p.tag}${total}`;
    }
    const total = p.min_games_total ? `, ${p.min_games_total} entre todos` : '';
    return `${challenge.label} · completar un juego de ${p.tag} cada uno${total}`;
  }
  if (challenge.kind === 'debt_reduction') {
    const what = p.mode === 'percent' ? `saldar el ${number(p.percent)} % de lo que te quedaba por jugar` : `completar ${p.games} ${p.games === 1 ? 'juego' : 'juegos'} de los que tenías empezados`;
    return `${challenge.label} · ${what} al empezar`;
  }
  if (challenge.kind === 'new_genre') {
    const what = p.mode === 'play' ? `jugar ${hoursLabel(p.hours * 3600)} a` : 'completar';
    return `${challenge.label} · ${what} un juego de ${p.genre} que no tuvieras antes`;
  }
  return challenge.label;
}

/** The group's total of a challenge as a part to draw (hours or games), or null when the challenge has none. */
export function totalPart(progress) {
  if (progress.total_target_count !== undefined) {
    return { count: progress.total_count, target_count: progress.total_target_count, done: progress.total_done };
  }
  if (progress.total_target_seconds !== undefined) {
    return { seconds: progress.total_seconds, target_seconds: progress.total_target_seconds, done: progress.total_done };
  }
  return null;
}

const ORDER ={ active: 0, upcoming: 1, finished: 2 };
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
