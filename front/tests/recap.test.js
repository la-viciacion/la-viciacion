import assert from 'node:assert/strict';
import { test } from 'node:test';
import { change, clampPick, isMonth, lastMonth, monthChoices, monthKey, parseHash, periodKey, periodLabel, pickOf, previousPeriod, recapHref, withKind, yearChoices } from '../js/lib/recap.js';

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

test('a period is a kind, a year and, for a month, the month; and back', () => {
  assert.deepEqual(pickOf('2026-09'), { kind: 'month', year: 2026, month: 9 });
  assert.deepEqual(pickOf('2026'), { kind: 'year', year: 2026, month: null });
  for (const period of ['2026-09', '2024-01', '2026']) assert.equal(periodKey(pickOf(period)), period);
});

test('the years on offer go from the running one to 2023', () => {
  assert.deepEqual(yearChoices(new Date(2026, 9, 18)), [2026, 2025, 2024, 2023]);
  assert.deepEqual(yearChoices(new Date(2027, 0, 2)), [2027, 2026, 2025, 2024, 2023]);
});

test('a past year has its twelve months, the running one only up to the running month', () => {
  const now = new Date(2026, 9, 18);
  assert.equal(monthChoices(2025, now).length, 12);
  assert.deepEqual(monthChoices(2026, now).map((m) => m.value), [1, 2, 3, 4, 5, 6, 7, 8, 9]); // October (the running month) is not there: it has not finished
  assert.deepEqual([monthChoices(2026, now)[0].label, monthChoices(2026, now)[8].label], ['Enero', 'Septiembre']);
});

test('January of the running year has no finished month to offer', () => {
  assert.deepEqual(monthChoices(2026, new Date(2026, 0, 15)), []);
});

test('a choice made invalid is moved to the nearest valid one', () => {
  const now = new Date(2026, 9, 18);
  assert.deepEqual(clampPick({ kind: 'month', year: 2026, month: 12 }, now), { kind: 'month', year: 2026, month: 9 });
  assert.deepEqual(clampPick({ kind: 'month', year: 2027, month: 3 }, now), { kind: 'month', year: 2026, month: 3 }); // a year that does not exist yet becomes the running one
  assert.deepEqual(clampPick({ kind: 'month', year: 2027, month: 12 }, now), { kind: 'month', year: 2026, month: 9 });
  assert.deepEqual(clampPick({ kind: 'month', year: 2020, month: 1 }, now), { kind: 'month', year: 2023, month: 1 });
  assert.deepEqual(clampPick({ kind: 'year', year: 2030, month: null }, now), { kind: 'year', year: 2026, month: null });
  assert.deepEqual(clampPick({ kind: 'month', year: 2025, month: 12 }, now), { kind: 'month', year: 2025, month: 12 });
});

test('the running month itself is refused too, like a month still further ahead', () => {
  const now = new Date(2026, 9, 18); // October 2026 is running
  assert.deepEqual(clampPick({ kind: 'month', year: 2026, month: 10 }, now), { kind: 'month', year: 2026, month: 9 });
});

test('in January, picking the running year as monthly falls back to December of the year before', () => {
  const now = new Date(2026, 0, 15);
  assert.deepEqual(clampPick({ kind: 'month', year: 2026, month: 1 }, now), { kind: 'month', year: 2025, month: 12 });
  assert.deepEqual(clampPick({ kind: 'month', year: 2026, month: 6 }, now), { kind: 'month', year: 2025, month: 12 });
});

test('moving from a year to a month starts at its last finished month; from a month to a year it keeps the year', () => {
  const now = new Date(2026, 9, 18);
  assert.deepEqual(withKind({ kind: 'year', year: 2025, month: null }, 'month', now), { kind: 'month', year: 2025, month: 12 });
  assert.deepEqual(withKind({ kind: 'year', year: 2026, month: null }, 'month', now), { kind: 'month', year: 2026, month: 9 });
  assert.deepEqual(withKind({ kind: 'month', year: 2025, month: 4 }, 'year', now), { kind: 'year', year: 2025, month: null });
});
