import assert from 'node:assert/strict';
import { test } from 'node:test';
import { amountLabel, blocks, daysUntil, hoursLabel, launchMonths, partTarget, partValue, percent, resultLine, summaryLine, timeLeft, totalPart } from '../js/lib/challenges.js';

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
