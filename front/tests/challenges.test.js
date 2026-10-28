import assert from 'node:assert/strict';
import { test } from 'node:test';
import { amountLabel, blocks, daysUntil, debtPreview, digest, digestLine, hoursLabel, launchMonths, medal, partTarget, partValue, percent, remainingLabel, resultLine, standing, summaryLine, timeLeft, totalPart } from '../js/lib/challenges.js';

const TODAY = new Date(2026, 9, 15, 12, 0); // 15 October 2026

test('seconds read as hours with at most a decimal', () => {
  assert.equal(hoursLabel(0), '0 h');
  assert.equal(hoursLabel(7 * 3600), '7 h');
  assert.equal(hoursLabel(9000), '2,5 h');
  assert.equal(hoursLabel(undefined), '0 h');
});

test('the share of a target is capped at a hundred and a target of zero is reached', () => {
  assert.equal(percent(3600, 7200), 50);
  assert.equal(percent(7199, 7200), 99);
  assert.equal(percent(10000, 7200), 100);
  assert.equal(percent(0, 7200), 0);
  assert.equal(percent(5, 0), 100);
});

test('days are counted from the start of today, in both directions', () => {
  assert.equal(daysUntil('2026-10-15', TODAY), 0);
  assert.equal(daysUntil('2026-10-31', TODAY), 16);
  assert.equal(daysUntil('2026-10-10', TODAY), -5);
});

test('the time left says where the challenge is', () => {
  const at = (status, starts_on, ends_on) => timeLeft({ status, starts_on, ends_on }, TODAY);
  assert.equal(at('active', '2026-10-01', '2026-10-31'), 'Quedan 16 días');
  assert.equal(at('active', '2026-10-01', '2026-10-16'), 'Queda 1 día');
  assert.equal(at('active', '2026-10-01', '2026-10-15'), 'Termina hoy');
  assert.equal(at('upcoming', '2026-10-16', '2026-10-31'), 'Empieza mañana');
  assert.equal(at('upcoming', '2026-11-01', '2026-11-30'), 'Empieza en 17 días');
  assert.equal(at('finished', '2026-09-01', '2026-09-30'), 'Terminado');
});

test('the months to launch for start at the running one and cross the year', () => {
  assert.deepEqual(launchMonths(TODAY, 4).map((m) => m.value), ['2026-10', '2026-11', '2026-12', '2027-01']);
  assert.equal(launchMonths(TODAY, 1)[0].label, 'Octubre 2026');
});

test('a result is told from the player\'s part and the group\'s total', () => {
  assert.equal(resultLine({ done: true, group_done: true }), 'Cumpliste tu parte y el grupo llegó al total');
  assert.equal(resultLine({ done: true, group_done: false }), 'Cumpliste tu parte');
  assert.equal(resultLine({ done: false, group_done: true }), 'El grupo llegó al total');
  assert.equal(resultLine({ done: false, group_done: false }), 'No se cumplió');
});

test('a part is counted in games or in hours', () => {
  assert.equal(amountLabel({ seconds: 3600, target_seconds: 7200 }), '1 h / 2 h');
  assert.equal(amountLabel({ count: 0, target_count: 1 }), '0 / 1 juego');
  assert.equal(amountLabel({ count: 1, target_count: 3 }), '1 / 3 juegos');
  assert.equal(partValue({ count: 2, target_count: 3 }), 2);
  assert.equal(partTarget({ seconds: 5, target_seconds: 9 }), 9);
});

test('a challenge is summarised by what it asks', () => {
  const base = { label: 'Probar un género', kind: 'new_genre' };
  assert.equal(summaryLine({ ...base, params: { genre: 'RPG', mode: 'play', hours: 2.5 } }), 'Probar un género · jugar 2,5 h a un juego de RPG que no tuvieras antes');
  assert.equal(summaryLine({ ...base, params: { genre: 'RPG', mode: 'complete' } }), 'Probar un género · completar un juego de RPG que no tuvieras antes');
  assert.match(summaryLine({ kind: 'game_of_month', label: 'Juego del mes', params: { min_hours_each: 5, min_hours_total: 20 } }), /mínimo 5 h cada uno y 20 h entre todos/);
});

test('the page is split into the group\'s, the viewer\'s and the others\', running ones first and few finished', () => {
  const group = (id, status) => ({ id, scope: 'group', status });
  const own = (id, owner, status = 'active') => ({ id, scope: 'user', owner: { id: owner }, status });
  const finished = Array.from({ length: 8 }, (_, i) => group(100 + i, 'finished'));
  const result = blocks([group(1, 'finished'), group(2, 'upcoming'), group(3, 'active'), own(4, 1), own(5, 2), ...finished], 1);
  assert.deepEqual(result.map((b) => b.key), ['group', 'mine', 'others']);
  assert.deepEqual(result[0].list.slice(0, 2).map((c) => c.id), [3, 2]);
  assert.equal(result[0].list.length, 2 + 5); // the running ones and the latest five finished
  assert.deepEqual(result[1].list.map((c) => c.id), [4]);
  assert.deepEqual(result[2].list.map((c) => c.id), [5]);
  assert.deepEqual(blocks([], 1).map((b) => b.key), ['group', 'mine']); // nobody else's: no block
});

test('a personal result says it was achieved and a group one how the group did', () => {
  assert.equal(resultLine({ scope: 'user', done: true }), 'Lo conseguiste');
  assert.equal(resultLine({ scope: 'user', done: false }), 'No se cumplió');
});

test('a themed challenge is summarised by its mode and its optional total', () => {
  const themed = (params) => summaryLine({ kind: 'themed', label: 'Temático', params });
  assert.equal(themed({ tag: 'Horror', mode: 'play', min_hours_each: 2 }), 'Temático · jugar 2 h cada uno a juegos de Horror');
  assert.equal(themed({ tag: 'Horror', mode: 'play', min_hours_each: 2, min_hours_total: 10 }), 'Temático · jugar 2 h cada uno a juegos de Horror y 10 h entre todos');
  assert.equal(themed({ tag: 'Horror', mode: 'complete' }), 'Temático · completar un juego de Horror cada uno');
  assert.equal(themed({ tag: 'Horror', mode: 'complete', min_games_total: 5 }), 'Temático · completar un juego de Horror cada uno, 5 entre todos');
});

test('the group total is drawn in hours or in games, and not at all when there is none', () => {
  assert.deepEqual(totalPart({ total_seconds: 3600, total_target_seconds: 7200, total_done: false }), { seconds: 3600, target_seconds: 7200, done: false });
  assert.deepEqual(totalPart({ total_count: 2, total_target_count: 5, total_done: false }), { count: 2, target_count: 5, done: false });
  assert.equal(totalPart({ players: [] }), null);
});

test('a debt challenge reads as a share of the debt paid', () => {
  const part = { percent: 12.5, target_percent: 25, paid_seconds: 1, initial_seconds: 2, done: false };
  assert.equal(amountLabel(part), '12,5 % / 25 %');
  assert.equal(partValue(part), 12.5);
  assert.equal(partTarget(part), 25);
  assert.equal(percent(partValue(part), partTarget(part)), 50);
  assert.match(summaryLine({ kind: 'debt_reduction', label: 'Bajar la deuda', params: { mode: 'percent', percent: 25 } }), /saldar el 25 % de lo que te quedaba por jugar al empezar/);
  assert.match(summaryLine({ kind: 'debt_reduction', label: 'Bajar la deuda', params: { mode: 'games', games: 1 } }), /completar 1 juego de los que tenías empezados/);
});

test('the preview of a debt goal tells the hours of a percentage and checks the games', () => {
  const debt = { seconds: 40 * 3600, games: 4, open_games: 5 };
  assert.equal(debtPreview('percent', 25, debt), 'El 25 % de tu deuda son unas 10 h (tu deuda ahora: 40 h en 4 juegos).');
  assert.equal(debtPreview('percent', 12.5, { ...debt, games: 1 }), 'El 12,5 % de tu deuda son unas 5 h (tu deuda ahora: 40 h en 1 juego).');
  assert.match(debtPreview('percent', 0, debt), /Elige entre 1 y 100/);
  assert.match(debtPreview('percent', 10, { seconds: 0, games: 0, open_games: 2 }), /ya pasan de su tiempo medio/);
  assert.match(debtPreview('games', 2, debt), /Tienes 5 juegos sin terminar; cerrar 2 es completar 2/);
  assert.match(debtPreview('games', 1, { ...debt, open_games: 1 }), /Tienes 1 juego sin terminar; cerrar 1 es completar uno/);
  assert.match(debtPreview('games', 9, debt), /Solo tienes 5 juegos sin terminar/);
  assert.match(debtPreview('percent', 10, { seconds: 0, games: 0, open_games: 0 }), /no hay deuda que saldar/);
});

const DAY_MS = 86400000;
const iso = (offset) => {
  const d = new Date(TODAY.getTime() + offset * DAY_MS);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const running = (part, { starts = -10, ends = 10, scope = 'group', taking_part = true } = {}) => ({
  id: 1, scope, status: 'active', taking_part, starts_on: iso(starts), ends_on: iso(ends),
  progress: { players: [{ user_id: 7, name: 'Yo', ...part }] },
});

test('what is left of a part is told in hours, games or a share of the debt', () => {
  assert.equal(remainingLabel({ seconds: 3600, target_seconds: 9000 }), 'Te faltan 1,5 h');
  assert.equal(remainingLabel({ count: 0, target_count: 1 }), 'Te falta 1 juego');
  assert.equal(remainingLabel({ count: 1, target_count: 3 }), 'Te faltan 2 juegos');
  assert.equal(remainingLabel({ percent: 12.5, target_percent: 25 }), 'Te falta saldar un 12,5 % más');
});

test('a part that is reached says so, running or finished', () => {
  const done = { seconds: 7200, target_seconds: 7200, done: true };
  assert.deepEqual(standing(running(done), 7, TODAY), { tone: 'done', text: 'Ya has cumplido tu parte' });
  assert.equal(standing({ ...running(done), status: 'finished' }, 7, TODAY).text, 'Cumpliste tu parte');
  assert.equal(standing({ ...running(done, { scope: 'user' }), status: 'finished' }, 7, TODAY).text, 'Lo conseguiste');
  assert.deepEqual(standing({ ...running({ seconds: 0, target_seconds: 7200, done: false }), status: 'finished' }, 7, TODAY), { tone: 'failed', text: 'No se cumplió' });
});

test('the last days are urgent whatever the pace', () => {
  const part = { seconds: 3600, target_seconds: 7200, done: false };
  assert.deepEqual(standing(running(part, { ends: 2 }), 7, TODAY), { tone: 'urgent', text: 'Quedan 2 días: te faltan 1 h' });
  assert.equal(standing(running(part, { ends: 1 }), 7, TODAY).text, 'Queda 1 día: te faltan 1 h');
  assert.equal(standing(running(part, { ends: 0 }), 7, TODAY).text, 'Último día: te faltan 1 h');
});

test('a declined duel is not a running challenge for the digest, and every tone has a place in the order', () => {
  const declined = duel(0, 0, { declined: true, progress: { players: [{ user_id: 7, name: 'Yo', seconds: 0, versus: true, done: false }] } });
  const urgent = { ...running({ seconds: 0, target_seconds: 7200, done: false }, { ends: 1 }), id: 2 };
  const result = digest([declined, urgent], 7, TODAY);
  assert.deepEqual(result.items.map((i) => i.challenge.id), [2]);
});

test('a part behind the share of time gone by is told so, one in step is not, and a single game is only pending', () => {
  // 20 days long, 10 gone: half the time
  assert.equal(standing(running({ seconds: 3600, target_seconds: 36000, done: false }), 7, TODAY).tone, 'behind');
  assert.equal(standing(running({ seconds: 18000, target_seconds: 36000, done: false }), 7, TODAY).tone, 'ok');
  assert.equal(standing(running({ count: 0, target_count: 1, done: false }), 7, TODAY).tone, 'pending');
  // too early to judge a pace
  assert.equal(standing(running({ seconds: 0, target_seconds: 36000, done: false }, { starts: -2, ends: 18 }), 7, TODAY).tone, 'ok');
});

test('nothing is said of a challenge the viewer does not take part in or that has not begun', () => {
  const part = { seconds: 0, target_seconds: 7200, done: false };
  assert.equal(standing(running(part, { taking_part: false }), 7, TODAY), null);
  assert.equal(standing({ ...running(part), status: 'upcoming' }, 7, TODAY), null);
});

test('the digest keeps the running ones that count for the viewer, the ones that need attention first', () => {
  const ok = running({ seconds: 18000, target_seconds: 36000, done: false });
  const urgent = { ...running({ seconds: 0, target_seconds: 7200, done: false }, { ends: 1 }), id: 2 };
  const done = { ...running({ seconds: 7200, target_seconds: 7200, done: true }), id: 3 };
  const finished = { ...running({ seconds: 0, target_seconds: 7200, done: false }), id: 4, status: 'finished' };
  const result = digest([done, ok, finished, urgent], 7, TODAY);
  assert.deepEqual(result.items.map((i) => i.challenge.id), [2, 1, 3]);
  assert.equal(result.done, 1);
  assert.equal(result.urgent, 1);
  assert.equal(digestLine(result), '3 retos en marcha · 1 cumplido · 1 con poco tiempo');
  assert.equal(digestLine(digest([], 7, TODAY)), '');
});

test('a count part names what it counts and the new kinds are summarised by what they ask', () => {
  assert.equal(amountLabel({ count: 3, target_count: 7, unit: 'days' }), '3 / 7 días');
  assert.equal(amountLabel({ count: 0, target_count: 1, unit: 'sessions' }), '0 / 1 sesión');
  assert.equal(amountLabel({ count: 1, target_count: 3, unit: 'genres' }), '1 / 3 géneros');
  assert.equal(amountLabel({ count: 1, target_count: 3 }), '1 / 3 juegos');
  assert.equal(remainingLabel({ count: 2, target_count: 3, unit: 'days' }), 'Te falta 1 día');
  assert.equal(remainingLabel({ count: 0, target_count: 3, unit: 'sessions' }), 'Te faltan 3 sesiones');
  const kind = (k, label, p) => summaryLine({ kind: k, label, params: p });
  assert.equal(kind('streak', 'Racha', { mode: 'consecutive', days: 7 }), 'Racha · jugar 7 días seguidos');
  assert.equal(kind('streak', 'Racha', { mode: 'days', days: 10 }), 'Racha · jugar 10 días distintos');
  assert.equal(kind('long_sessions', 'Sesiones largas', { sessions: 1, minutes: 90 }), 'Sesiones largas · 1 sesión de al menos 90 min');
  assert.equal(kind('variety', 'Variar de género', { genres: 3, hours: 1.5 }), 'Variar de género · jugar al menos 1,5 h a 3 géneros distintos');
  assert.match(kind('wishlist', 'Cumplir deseados', { mode: 'start', games: 2 }), /empezar 2 juegos de los que esperabas en deseados/);
});

const duel = (me, other, extra = {}) => ({
  id: 9, kind: 'duel_hours', label: 'Duelo de horas', scope: 'duel', status: 'active', declined: false, taking_part: true,
  starts_on: iso(-2), ends_on: iso(5), owner: { id: 7, name: 'Yo' }, opponent: { id: 8, name: 'Bea' }, params: { opponent_id: 8 },
  progress: { players: [{ user_id: 7, name: 'Yo', seconds: me, versus: true, done: me > other }, { user_id: 8, name: 'Bea', seconds: other, versus: true, done: other > me }] },
  ...extra,
});

test('a duel says who is ahead and by how much, from either side', () => {
  assert.deepEqual(standing(duel(7200, 3600), 7, TODAY), { tone: 'ok', text: 'Vas ganando a Bea por 1 h' });
  assert.deepEqual(standing(duel(3600, 7200), 7, TODAY), { tone: 'behind', text: 'Vas perdiendo contra Bea por 1 h' });
  assert.deepEqual(standing(duel(3600, 3600), 7, TODAY), { tone: 'pending', text: 'Empatados con Bea' });
  const asBea = standing(duel(7200, 3600), 8, TODAY);
  assert.deepEqual(asBea, { tone: 'behind', text: 'Vas perdiendo contra Yo por 1 h' });
});

test('losing a duel in the last days is urgent', () => {
  assert.equal(standing(duel(0, 3600, { ends_on: iso(1) }), 7, TODAY).tone, 'urgent');
});

test('a finished duel says who won, a tie, or that nobody played', () => {
  const done = (me, other) => standing({ ...duel(me, other), status: 'finished' }, 7, TODAY);
  assert.deepEqual(done(7200, 3600), { tone: 'done', text: 'Ganaste el duelo a Bea' });
  assert.deepEqual(done(3600, 7200), { tone: 'failed', text: 'Perdiste el duelo contra Bea' });
  assert.deepEqual(done(3600, 3600), { tone: 'done', text: 'Empate: ganáis los dos' });
  assert.deepEqual(done(0, 0), { tone: 'failed', text: 'Nadie jugó: sin ganador' });
});

test('a declined duel is told to the challenger and to nobody else', () => {
  const declined = duel(0, 0, { declined: true, progress: { players: [{ user_id: 7, name: 'Yo', seconds: 0, versus: true, done: false }] } });
  assert.deepEqual(standing(declined, 7, TODAY), { tone: 'failed', text: 'Bea ha rechazado el duelo' });
  assert.equal(standing({ ...declined, taking_part: false }, 8, TODAY), null);
});

test('a versus group challenge adds the position, a duel part shows only its hours', () => {
  const part = { user_id: 7, name: 'Yo', seconds: 3600, target_seconds: 18000, done: false, position: 2 };
  const versus = { ...running(part, { starts: -2, ends: 18 }), params: { versus: true } };
  assert.match(standing(versus, 7, TODAY).text, /· 🥈$/);
  assert.equal(medal(1), '🥇');
  assert.equal(medal(4), '4º');
  assert.equal(amountLabel({ seconds: 5400, target_seconds: 7200, versus: true }), '1,5 h');
});

test('the duels of the viewer have their own block and the others go with the other players', () => {
  const mine = duel(0, 0);
  const asked = duel(0, 0, { id: 10, owner: { id: 8, name: 'Bea' }, opponent: { id: 7, name: 'Yo' } });
  const other = duel(0, 0, { id: 11, owner: { id: 8, name: 'Bea' }, opponent: { id: 9, name: 'Cris' } });
  const result = blocks([mine, asked, other], 7);
  assert.deepEqual(result.map((b) => b.key), ['group', 'mine', 'duels', 'others']);
  assert.deepEqual(result.find((b) => b.key === 'duels').list.map((c) => c.id), [9, 10]);
  assert.deepEqual(result.find((b) => b.key === 'others').list.map((c) => c.id), [11]);
});

test('a duel result is told as a win, a loss or a tie, and the duels are summarised', () => {
  assert.equal(resultLine({ scope: 'duel', done: true, tied: false }), 'Ganaste el duelo');
  assert.equal(resultLine({ scope: 'duel', done: false, tied: false }), 'Perdiste el duelo');
  assert.equal(resultLine({ scope: 'duel', done: true, tied: true }), 'Empate');
  assert.equal(summaryLine({ kind: 'duel_hours', label: 'Duelo de horas', params: {} }), 'Duelo de horas · gana quien juegue más horas');
  assert.equal(summaryLine({ kind: 'duel_game', label: 'Duelo en un juego', game: { name: 'Hades' }, params: {} }), 'Duelo en un juego · gana quien juegue más a Hades');
  const versus = summaryLine({ kind: 'game_of_month', label: 'Juego del mes', params: { min_hours_each: 5, min_hours_total: 12, versus: true } });
  assert.match(versus, /y gana quien más avance$/);
});

const countDuel = (me, other, extra = {}) => ({
  ...duel(0, 0),
  kind: 'duel_completed',
  label: 'Duelo de completados',
  progress: { players: [
    { user_id: 7, name: 'Yo', count: me, target_count: Math.max(me, other), unit: 'games', versus: true, done: me > other },
    { user_id: 8, name: 'Bea', count: other, target_count: Math.max(me, other), unit: 'games', versus: true, done: other > me },
  ] },
  ...extra,
});

test('a duel of completed games counts games, running or finished', () => {
  assert.deepEqual(standing(countDuel(3, 1), 7, TODAY), { tone: 'ok', text: 'Vas ganando a Bea por 2 juegos' });
  assert.deepEqual(standing(countDuel(1, 2), 7, TODAY), { tone: 'behind', text: 'Vas perdiendo contra Bea por 1 juego' });
  assert.equal(standing(countDuel(0, 1, { ends_on: iso(1) }), 7, TODAY).tone, 'urgent');
  const done = (me, other) => standing({ ...countDuel(me, other), status: 'finished' }, 7, TODAY);
  assert.deepEqual(done(2, 1), { tone: 'done', text: 'Ganaste el duelo a Bea' });
  assert.deepEqual(done(0, 0), { tone: 'failed', text: 'Nadie completó nada: sin ganador' });
  assert.equal(amountLabel({ count: 1, target_count: 3, unit: 'games', versus: true }), '1 juego');
  assert.equal(amountLabel({ count: 3, target_count: 3, unit: 'games', versus: true }), '3 juegos');
});

test('the new kinds are summarised by what they ask', () => {
  const kind = (k, label, p) => summaryLine({ kind: k, label, params: p });
  assert.equal(kind('duel_completed', 'Duelo de completados', {}), 'Duelo de completados · gana quien complete más juegos');
  assert.equal(kind('finish_backlog', 'Terminar lo empezado', { games: 1 }), 'Terminar lo empezado · completar 1 juego de los que ya tenías empezados');
  assert.equal(kind('finish_backlog', 'Terminar lo empezado', { games: 3 }), 'Terminar lo empezado · completar 3 juegos de los que ya tenías empezados');
  assert.match(kind('finish_first', 'Terminar antes de empezar', {}), /sin empezar ninguno nuevo antes; si empiezas uno nuevo, se pierde$/);
  assert.equal(kind('group_hours', 'Horas entre todos', { min_hours_total: 40 }), 'Horas entre todos · jugar 40 h entre todos, a lo que sea');
  assert.match(kind('group_hours', 'Horas entre todos', { min_hours_total: 40, versus: true }), /y gana quien más avance$/);
});

test('a challenge lost before it was won says so, running or finished, and the win is the usual one', () => {
  const lost = { count: 0, target_count: 1, unit: 'games', done: false, failed: true };
  assert.deepEqual(standing(running(lost, { scope: 'user' }), 7, TODAY), { tone: 'failed', text: 'Perdido: empezaste un juego nuevo antes de terminar uno' });
  assert.equal(standing({ ...running(lost, { scope: 'user' }), status: 'finished' }, 7, TODAY).text, 'Se perdió: empezaste un juego nuevo antes de terminar uno');
  const won = { count: 1, target_count: 1, unit: 'games', done: true, failed: false };
  assert.equal(standing({ ...running(won, { scope: 'user' }), status: 'finished' }, 7, TODAY).text, 'Lo conseguiste');
  assert.equal(standing(running({ ...won, count: 0, done: false, failed: false }, { scope: 'user' }), 7, TODAY).tone, 'pending');
});

const hoursChallenge = (part, progress, extra = {}) => ({
  ...running({ seconds: 0, target_seconds: 40 * 3600, contribution: true, done: false, ...part }),
  progress: { players: [{ user_id: 7, name: 'Yo', seconds: 0, target_seconds: 40 * 3600, contribution: true, done: false, ...part }], total_seconds: 0, total_target_seconds: 40 * 3600, total_done: false, ...progress },
  ...extra,
});

test('the share a player puts in the group\'s hours is read against the group\'s total', () => {
  assert.equal(amountLabel({ seconds: 5400, target_seconds: 144000, contribution: true }), '1,5 h');
  // 20 days long, 10 gone: the group has 5 h of 40
  assert.deepEqual(standing(hoursChallenge({ seconds: 3600 }, { total_seconds: 5 * 3600 }), 7, TODAY), { tone: 'behind', text: 'El grupo va por detrás del ritmo: faltan 35 h' });
  assert.deepEqual(standing(hoursChallenge({ seconds: 3600 }, { total_seconds: 25 * 3600 }), 7, TODAY), { tone: 'ok', text: 'Al grupo le faltan 15 h' });
  assert.deepEqual(standing(hoursChallenge({ seconds: 3600 }, { total_seconds: 25 * 3600 }, { ends_on: iso(1) }), 7, TODAY), { tone: 'urgent', text: 'Queda 1 día: faltan 15 h al grupo' });
  assert.deepEqual(standing(hoursChallenge({ seconds: 3600, done: true }, { total_seconds: 41 * 3600, total_done: true }), 7, TODAY), { tone: 'done', text: 'El grupo ya ha llegado al total' });
  assert.equal(standing(hoursChallenge({ seconds: 0 }, { total_seconds: 41 * 3600, total_done: true }), 7, TODAY).tone, 'pending');
});

test('a finished group total is met by whoever put something in', () => {
  const finished = (part, progress) => ({ ...hoursChallenge(part, progress), status: 'finished' });
  assert.deepEqual(standing(finished({ seconds: 3600, done: true }, { total_done: true }), 7, TODAY), { tone: 'done', text: 'El grupo llegó al total' });
  assert.equal(standing(finished({ seconds: 0 }, { total_done: true }), 7, TODAY).text, 'El grupo llegó al total, pero no aportaste');
  assert.equal(standing(finished({ seconds: 3600 }, { total_done: false }), 7, TODAY).text, 'El grupo no llegó al total');
});
