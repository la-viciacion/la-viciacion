import assert from 'node:assert/strict';
import { test } from 'node:test';
import { paceLines } from '../js/lib/pace.js';

const H = 3600;

test('nothing to say without a pace', () => {
  assert.deepEqual(paceLines(null), []);
});

test('a completed game says how much faster or slower than the group and than HowLongToBeat', () => {
  const lines = paceLines({ seconds: 6 * H, completed: true, group_mean: 8 * H, group_count: 3, group_share: 75, avg_time: 5 * H, avg_share: 120 });
  assert.equal(lines[0], 'Lo completaste con 6 h de juego.');
  assert.match(lines[1], /Eres un 25 % más rápido que el resto del grupo: 8 h de media \(3 jugadores lo han completado\)\./);
  assert.match(lines[2], /Eres un 20 % más lento que HowLongToBeat \(5 h\)\./);
});

test('the same time is "igual que" and one player is told in the singular', () => {
  const lines = paceLines({ seconds: 4 * H, completed: true, group_mean: 4 * H, group_count: 1, group_share: 100, avg_time: null, avg_share: null });
  assert.match(lines[1], /Eres igual que el resto del grupo: 4 h de media \(1 jugador lo ha completado\)/);
  assert.equal(lines.length, 2); // no average time, no line about it
});

test('a game still being played says what share of the reference time it is', () => {
  const lines = paceLines({ seconds: 2 * H, completed: false, group_mean: 10 * H, group_count: 2, group_share: 20, avg_time: 8 * H, avg_share: 25 });
  assert.equal(lines[0], 'Llevas 2 h de juego.');
  assert.match(lines[1], /Es el 20 % de lo que ha tardado el resto del grupo: 10 h de media/);
  assert.match(lines[2], /Es el 25 % del tiempo medio de HowLongToBeat \(8 h\)/);
});

test('with nobody to compare with and no average only the time is told', () => {
  assert.deepEqual(paceLines({ seconds: H, completed: false, group_mean: null, group_count: 0, group_share: null, avg_time: null, avg_share: null }), ['Llevas 1 h de juego.']);
});
