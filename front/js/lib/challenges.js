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

/** "Todavía no se ha apuntado nadie", "Se ha apuntado 1 jugador", "Se han apuntado 3 jugadores": who joined a voluntary challenge. */
export function joinedLine(count) {
  if (!count) return 'Todavía no se ha apuntado nadie';
  return count === 1 ? 'Se ha apuntado 1 jugador' : `Se han apuntado ${count} jugadores`;
}

/** What a themed challenge says about its games: `theme_games` is { available, mine } (the games of its theme in the
 * group's libraries, and how many the viewer has). { text, tone }: the tone is "urgent" when the viewer has none, since
 * then they have to buy one, leave the challenge or not join it. */
export function themeGamesLine({ available, mine }) {
  const games = (n) => (n === 1 ? '1 juego' : `${n} juegos`);
  if (!available) return { text: 'Ningún juego de esta temática está en las bibliotecas del grupo.', tone: 'urgent' };
  if (!mine) return { text: `El grupo tiene ${games(available)} de esta temática y tú no tienes ninguno.`, tone: 'urgent' };
  if (mine === available) return { text: available === 1 ? 'Tienes el único juego de esta temática del grupo.' : `Tienes los ${available} juegos de esta temática del grupo.`, tone: 'ok' };
  return { text: `Tienes ${mine} de los ${available} juegos de esta temática del grupo.`, tone: 'ok' };
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

// What a count part counts: games unless the part says (`unit`, from the API), as [singular, plural]
const UNITS = { games: ['juego', 'juegos'], days: ['día', 'días'], sessions: ['sesión', 'sesiones'], genres: ['género', 'géneros'] };
const unitName = (part, n) => (UNITS[part.unit] ?? UNITS.games)[n === 1 ? 0 : 1];

/** "3 / 5 h", "0 / 1 juego", "3 / 7 días" or "12,5 % / 25 %"; a duel or a share of a group's total says only what was reached */
export function amountLabel(part) {
  if (part.versus || part.contribution) return isCount(part) ? `${part.count} ${unitName(part, part.count)}` : hoursLabel(part.seconds);
  if (isCount(part)) return `${part.count} / ${part.target_count} ${unitName(part, part.target_count)}`;
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

const versusNote = (challenge) => (challenge.params?.versus ? ' · y gana quien más avance' : '');

/** 1 -> "🥇", 2 -> "🥈", 3 -> "🥉", then "4º" (a versus challenge ranks its players). */
export const medal = (position) => ['🥇', '🥈', '🥉'][position - 1] ?? `${position}º`;

/** What a challenge asks, in a line. */
export function summaryLine(challenge) {
  const p = challenge.params;
  if (challenge.kind === 'game_of_month') {
    return `${challenge.label} · mínimo ${hoursLabel(p.min_hours_each * 3600)} cada uno y ${hoursLabel(p.min_hours_total * 3600)} entre todos${versusNote(challenge)}`;
  }
  if (challenge.kind === 'themed') {
    if (p.mode === 'play') {
      const total = p.min_hours_total ? ` y ${hoursLabel(p.min_hours_total * 3600)} entre todos` : '';
      return `${challenge.label} · jugar ${hoursLabel(p.min_hours_each * 3600)} cada uno a juegos de ${p.theme ?? p.tag}${total}${versusNote(challenge)}`;
    }
    const total = p.min_games_total ? `, ${p.min_games_total} entre todos` : '';
    return `${challenge.label} · completar un juego de ${p.theme ?? p.tag} cada uno${total}${versusNote(challenge)}`;
  }
  if (challenge.kind === 'debt_reduction') {
    const what = p.mode === 'percent' ? `saldar el ${number(p.percent)} % de lo que te quedaba por jugar` : `completar ${p.games} ${p.games === 1 ? 'juego' : 'juegos'} de los que tenías empezados`;
    return `${challenge.label} · ${what} al empezar`;
  }
  if (challenge.kind === 'new_genre') {
    const what = p.mode === 'play' ? `jugar ${hoursLabel(p.hours * 3600)} a` : 'completar';
    return `${challenge.label} · ${what} un juego de ${p.genre} que no tuvieras antes`;
  }
  if (challenge.kind === 'group_hours') {
    return `${challenge.label} · jugar ${hoursLabel(p.min_hours_total * 3600)} entre todos, a lo que sea${versusNote(challenge)}`;
  }
  if (challenge.kind === 'finish_backlog') {
    return `${challenge.label} · completar ${p.games} ${p.games === 1 ? 'juego' : 'juegos'} de los que ya tenías empezados`;
  }
  if (challenge.kind === 'finish_first') {
    return `${challenge.label} · completar un juego que ya tenías empezado sin empezar ninguno nuevo antes; si empiezas uno nuevo, se pierde`;
  }
  if (challenge.kind === 'duel_completed') return `${challenge.label} · gana quien complete más juegos`;
  if (challenge.kind === 'duel_hours') return `${challenge.label} · gana quien juegue más horas`;
  if (challenge.kind === 'duel_game') return `${challenge.label} · gana quien juegue más a ${challenge.game?.name ?? 'ese juego'}`;
  if (challenge.kind === 'streak') {
    return `${challenge.label} · jugar ${p.days} días ${p.mode === 'consecutive' ? 'seguidos' : 'distintos'}`;
  }
  if (challenge.kind === 'long_sessions') {
    return `${challenge.label} · ${p.sessions} ${p.sessions === 1 ? 'sesión' : 'sesiones'} de al menos ${p.minutes} min`;
  }
  if (challenge.kind === 'variety') {
    return `${challenge.label} · jugar al menos ${hoursLabel(p.hours * 3600)} a ${p.genres} géneros distintos`;
  }
  if (challenge.kind === 'wishlist') {
    return `${challenge.label} · ${p.mode === 'start' ? 'empezar' : 'completar'} ${p.games} ${p.games === 1 ? 'juego' : 'juegos'} de los que esperabas en deseados`;
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

/** What is left of a part, in words: "Te faltan 1,5 h", "Te falta 1 juego", "Te falta saldar un 12,5 % más". */
export function remainingLabel(part) {
  if (isCount(part)) {
    const left = part.target_count - part.count;
    return left === 1 ? `Te falta 1 ${unitName(part, 1)}` : `Te faltan ${left} ${unitName(part, left)}`;
  }
  if (isPercent(part)) return `Te falta saldar un ${number(Math.round((part.target_percent - part.percent) * 10) / 10)} % más`;
  return `Te faltan ${hoursLabel(part.target_seconds - part.seconds)}`;
}

// Where a player's part stands, from the sessions already counted: a part is "behind" when what it has reached trails
// the share of the period that has gone by, and "urgent" in the last days. A goal of a single game is just pending: a
// pace means nothing when it is all or nothing.
const URGENT_DAYS = 2;
const PACE_FROM = 0.3;
const PACE_GAP = 0.2;

/** How the viewer is doing in a challenge, for the notice the card shows: { tone, text }, or null when they do not
 * take part or it has not begun. Tones: done, failed, urgent, behind, ok, pending. */
export function standing(challenge, meId, today = new Date()) {
  const result = baseStanding(challenge, meId, today);
  const part = challenge.progress.players.find((p) => p.user_id === meId);
  return result && challenge.params?.versus && part?.position ? { ...result, text: `${result.text} · ${medal(part.position)}` } : result;
}

/** A duel from the point of view of one of its two players. */
function duelStanding(challenge, meId, today) {
  const me = challenge.progress.players.find((p) => p.user_id === meId);
  const other = challenge.progress.players.find((p) => p.user_id !== meId);
  const rival = (meId === challenge.owner?.id ? challenge.opponent : challenge.owner)?.name ?? 'tu rival';
  if (challenge.declined) return meId === challenge.owner?.id ? { tone: 'failed', text: `${rival} ha rechazado el duelo` } : null;
  if (!me || !other || challenge.status === 'upcoming') return null;
  const [mine, theirs] = [partValue(me), partValue(other)];
  const counted = isCount(me);
  const amount = (n) => (counted ? `${n} ${unitName(me, n)}` : hoursLabel(n));
  if (challenge.status === 'finished') {
    if (!mine && !theirs) return { tone: 'failed', text: counted ? 'Nadie completó nada: sin ganador' : 'Nadie jugó: sin ganador' };
    if (mine === theirs) return { tone: 'done', text: 'Empate: ganáis los dos' };
    return me.done ? { tone: 'done', text: `Ganaste el duelo a ${rival}` } : { tone: 'failed', text: `Perdiste el duelo contra ${rival}` };
  }
  const gap = mine - theirs;
  if (gap === 0) return { tone: 'pending', text: `Empatados con ${rival}` };
  if (gap > 0) return { tone: 'ok', text: `Vas ganando a ${rival} por ${amount(gap)}` };
  const days = daysUntil(challenge.ends_on, today);
  return { tone: days <= URGENT_DAYS ? 'urgent' : 'behind', text: `Vas perdiendo contra ${rival} por ${amount(-gap)}` };
}

/** The viewer's part in a group's total of hours (every part puts something in; the goal is the group's, not theirs). */
function contributionStanding(challenge, part, today) {
  const { total_seconds: total, total_target_seconds: target, total_done: reached } = challenge.progress;
  if (challenge.status === 'finished') {
    if (part.done) return { tone: 'done', text: 'El grupo llegó al total' };
    return { tone: 'failed', text: reached ? 'El grupo llegó al total, pero no aportaste' : 'El grupo no llegó al total' };
  }
  if (part.done) return { tone: 'done', text: 'El grupo ya ha llegado al total' };
  if (reached) return { tone: 'pending', text: 'El grupo ya ha llegado al total: aporta algo para que cuente' };
  const left = hoursLabel(target - total);
  const days = daysUntil(challenge.ends_on, today);
  if (days <= URGENT_DAYS) return { tone: 'urgent', text: `${days <= 0 ? 'Último día' : days === 1 ? 'Queda 1 día' : `Quedan ${days} días`}: faltan ${left} al grupo` };
  const length = daysUntil(challenge.ends_on, parseDay(challenge.starts_on)) + 1;
  const elapsed = (length - days) / length;
  return elapsed >= PACE_FROM && total / target < elapsed - PACE_GAP
    ? { tone: 'behind', text: `El grupo va por detrás del ritmo: faltan ${left}` }
    : { tone: 'ok', text: `Al grupo le faltan ${left}` };
}

function baseStanding(challenge, meId, today) {
  if (challenge.scope === 'duel') return duelStanding(challenge, meId, today);
  const part = challenge.taking_part ? challenge.progress.players.find((p) => p.user_id === meId) : null;
  if (!part || challenge.status === 'upcoming') return null;
  if (part.contribution) return contributionStanding(challenge, part, today);
  if (part.failed) return { tone: 'failed', text: challenge.status === 'finished' ? 'Se perdió: empezaste un juego nuevo antes de terminar uno' : 'Perdido: empezaste un juego nuevo antes de terminar uno' };
  if (challenge.status === 'finished') {
    return part.done ? { tone: 'done', text: challenge.scope === 'user' ? 'Lo conseguiste' : 'Cumpliste tu parte' } : { tone: 'failed', text: 'No se cumplió' };
  }
  if (part.done) return { tone: 'done', text: 'Ya has cumplido tu parte' };
  const left = remainingLabel(part);
  const days = daysUntil(challenge.ends_on, today);
  if (days <= URGENT_DAYS) return { tone: 'urgent', text: `${days <= 0 ? 'Último día' : days === 1 ? 'Queda 1 día' : `Quedan ${days} días`}: ${left.toLowerCase()}` };
  if (isCount(part) && part.target_count === 1) return { tone: 'pending', text: left };
  const length = daysUntil(challenge.ends_on, parseDay(challenge.starts_on)) + 1;
  const elapsed = (length - days) / length;
  const reached = partValue(part) / partTarget(part);
  if (elapsed >= PACE_FROM && reached < elapsed - PACE_GAP) return { tone: 'behind', text: `Vas por detrás del ritmo: ${left.toLowerCase()}` };
  return { tone: 'ok', text: `Vas bien: ${left.toLowerCase()}` };
}

const TONE_ORDER = { urgent: 0, behind: 1, pending: 2, ok: 3, done: 4, failed: 5 };

/** The viewer's running challenges with how they stand, the ones that need attention first:
 * { items: [{ challenge, standing }], done, urgent } (what the Home card and the top of the page say). */
export function digest(challenges, meId, today = new Date()) {
  const items = challenges
    .filter((c) => c.status === 'active' && !c.declined)
    .map((challenge) => ({ challenge, standing: standing(challenge, meId, today) }))
    .filter((item) => item.standing)
    .sort((a, b) => TONE_ORDER[a.standing.tone] - TONE_ORDER[b.standing.tone]);
  return {
    items,
    done: items.filter((i) => i.standing.tone === 'done').length,
    urgent: items.filter((i) => i.standing.tone === 'urgent').length,
  };
}

/** "3 retos en marcha · 1 cumplido · 1 con poco tiempo" (empty when there are none). */
export function digestLine({ items, done, urgent }) {
  if (!items.length) return '';
  const parts = [items.length === 1 ? '1 reto en marcha' : `${items.length} retos en marcha`];
  if (done) parts.push(done === 1 ? '1 cumplido' : `${done} cumplidos`);
  if (urgent) parts.push(`${urgent} con poco tiempo`);
  return parts.join(' · ');
}

const ORDER ={ active: 0, upcoming: 1, finished: 2 };
export const FINISHED_SHOWN = 5;

/** The page's blocks: the group's challenges, the viewer's own and the other players', each with the running ones
 * first and only the latest `shown` finished ones. [{ key, title, list, empty }] (the others' block only when there is one). */
export function blocks(challenges, meId, shown = FINISHED_SHOWN) {
  const sorted = (list) => [...list].sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const cut = (list) => [...sorted(list).filter((c) => c.status !== 'finished'), ...sorted(list).filter((c) => c.status === 'finished').slice(0, shown)];
  const group = challenges.filter((c) => c.scope === 'group');
  const mine = challenges.filter((c) => c.scope === 'user' && c.owner?.id === meId);
  const isMyDuel = (c) => c.scope === 'duel' && (c.owner?.id === meId || c.opponent?.id === meId);
  const duels = challenges.filter(isMyDuel);
  const others = challenges.filter((c) => (c.scope === 'user' && c.owner?.id !== meId) || (c.scope === 'duel' && !isMyDuel(c)));
  return [
    { key: 'group', title: 'Del grupo', list: cut(group), empty: 'No hay ningún reto del grupo.' },
    { key: 'mine', title: 'Tuyos', list: cut(mine), empty: 'No tienes ningún reto. Lanza uno con «Nuevo reto».' },
    ...(duels.length ? [{ key: 'duels', title: 'Duelos', list: cut(duels), empty: '' }] : []),
    ...(others.length ? [{ key: 'others', title: 'De otros jugadores', list: cut(others), empty: '' }] : []),
  ];
}

/** The personal kinds a player can launch, for the form: [value, label]. */
export const PERSONAL_KINDS = [
  ['new_genre', 'Probar un género'],
  ['debt_reduction', 'Bajar la deuda'],
  ['streak', 'Racha'],
  ['long_sessions', 'Sesiones largas'],
  ['variety', 'Variar de género'],
  ['wishlist', 'Cumplir deseados'],
  ['finish_backlog', 'Terminar lo empezado'],
  ['finish_first', 'Terminar antes de empezar'],
  ['duel_hours', 'Duelo de horas'],
  ['duel_game', 'Duelo en un juego'],
  ['duel_completed', 'Duelo de completados'],
];

/** The group challenges a player can propose, for the form: [value, label]. */
export const PROPOSAL_KINDS = [['game_of_month', 'Juego del mes'], ['themed', 'Temático']];

/** What the player reads of a proposal: { label, detail } (the answer of the admins, if there is one). */
export function proposalStatus(proposal) {
  if (proposal.status === 'approved') return { label: 'Aprobada', detail: 'Ya es un reto del grupo: míralo arriba.' };
  if (proposal.status === 'rejected') return { label: 'Rechazada', detail: proposal.decision_note ? `Nota: ${proposal.decision_note}` : 'Sin nota.' };
  return { label: 'Esperando respuesta', detail: '' };
}

/** How long a personal challenge lasts, to choose from. */
export const DURATIONS = [['week', 'Una semana'], ['month', 'Un mes'], ['quarter', 'Tres meses']];

/** The line a finished challenge gets in a player's history. */
export function resultLine(entry) {
  if (entry.scope === 'duel') return entry.tied ? 'Empate' : entry.done ? 'Ganaste el duelo' : 'Perdiste el duelo';
  if (entry.scope === 'user') return entry.done ? 'Lo conseguiste' : 'No se cumplió';
  if (entry.done) return entry.group_done ? 'Cumpliste tu parte y el grupo llegó al total' : 'Cumpliste tu parte';
  return entry.group_done ? 'El grupo llegó al total' : 'No se cumplió';
}
