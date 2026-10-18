import assert from 'node:assert/strict';
import { test } from 'node:test';
import { change, isMonth, lastMonth, monthKey, parseHash, periodChoices, periodLabel, previousPeriod, recapHref } from '../js/lib/recap.js';

test('a month and a season are told apart and named', () => {
  assert.equal(isMonth('2026-09'), true);
  assert.equal(isMonth('2026'), false);
  assert.equal(periodLabel('2026-09'), 'septiembre de 2026');
  assert.equal(periodLabel('2026'), 'temporada 2026');
});

test('the recap opens on the month that has just ended, also in January', () => {
  assert.equal(lastMonth(new Date(2026, 9, 18)), '2026-09');
  assert.equal(lastMonth(new Date(2027, 0, 5)), '2026-12');
  assert.equal(monthKey(new Date(2026, 2, 1)), '2026-03');
});

test('the period before', () => {
  assert.equal(previousPeriod('2026-03'), '2026-02');
  assert.equal(previousPeriod('2026-01'), '2025-12');
  assert.equal(previousPeriod('2026'), '2025');
});

test('the selector offers every month from the running one back to 2023, and the seasons', () => {
  const { months, seasons } = periodChoices(new Date(2026, 9, 18));
  assert.equal(months[0].value, '2026-10');
  assert.equal(months.at(-1).value, '2023-01');
  assert.equal(months.length, 3 * 12 + 10);
  assert.deepEqual(seasons.map((s) => s.value), ['2026', '2025', '2024', '2023']);
});

test('an address goes there and back', () => {
  assert.equal(recapHref('2026-09'), '#/recap/2026-09');
  assert.equal(recapHref('2026', 'a b'), '#/recap/2026/a%20b');
  assert.deepEqual(parseHash('#/recap'), { period: null, username: null });
  assert.deepEqual(parseHash('#/recap/2026-09'), { period: '2026-09', username: null });
  assert.deepEqual(parseHash('#/recap/2026/a%20b'), { period: '2026', username: 'a b' });
  assert.deepEqual(parseHash('#/recap/2026-13'), { period: null, username: null }); // not a month: nothing is taken from it
  assert.deepEqual(parseHash('#/other'), { period: null, username: null });
});

test('a figure says how it moved', () => {
  const hours = (n) => `${n}s`;
  assert.deepEqual(change(10, 4, hours), { text: '+6s', trend: 'up' });
  assert.deepEqual(change(4, 10, hours), { text: '−6s', trend: 'down' });
  assert.deepEqual(change(5, 5, hours), { text: 'igual', trend: 'same' });
});
