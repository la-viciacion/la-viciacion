import assert from 'node:assert/strict';
import { test } from 'node:test';
import { daysUntil, hoursLabel, launchMonths, percent, resultLine, timeLeft } from '../js/lib/challenges.js';

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
