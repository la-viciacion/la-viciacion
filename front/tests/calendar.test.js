import assert from 'node:assert/strict';
import { test } from 'node:test';
import { byDay, monthLabel, monthOf, monthWeeks, shiftMonth, waiting } from '../js/lib/calendar.js';

test('months are moved across the year change', () => {
  assert.equal(shiftMonth('2026-12', 1), '2027-01');
  assert.equal(shiftMonth('2027-01', -1), '2026-12');
  assert.equal(shiftMonth('2026-10', 0), '2026-10');
  assert.equal(shiftMonth('2026-10', 14), '2027-12');
  assert.equal(monthOf(new Date(2026, 0, 31)), '2026-01');
});

test('a month is named in Spanish with a capital', () => {
  assert.equal(monthLabel('2026-10'), 'Octubre 2026');
});

test('the weeks start on Monday and the cells outside the month are empty', () => {
  const weeks = monthWeeks('2026-10'); // 1 October 2026 is a Thursday
  assert.deepEqual(weeks[0], [null, null, null, '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04']);
  assert.equal(weeks.at(-1).at(-1), null); // 31 October is a Saturday
  assert.equal(weeks.at(-1)[5], '2026-10-31');
  assert.ok(weeks.every((week) => week.length === 7));
  assert.equal(weeks.flat().filter(Boolean).length, 31);
});

test('a month that starts on Monday has no leading blanks, and February knows its leap year', () => {
  assert.equal(monthWeeks('2026-06')[0][0], '2026-06-01');
  assert.equal(monthWeeks('2028-02').flat().filter(Boolean).length, 29);
  assert.equal(monthWeeks('2027-02').flat().filter(Boolean).length, 28);
});

test('the releases are grouped by day', () => {
  const days = byDay([{ id: 'a', release_date: '2026-10-05' }, { id: 'b', release_date: '2026-10-05' }, { id: 'c', release_date: '2026-10-09' }]);
  assert.deepEqual(Object.keys(days), ['2026-10-05', '2026-10-09']);
  assert.deepEqual(days['2026-10-05'].map((g) => g.id), ['a', 'b']);
});

test('who waits for a game, with the viewer as "tú"', () => {
  assert.equal(waiting([]), '');
  assert.equal(waiting([{ name: 'Bea', is_me: false }]), 'Lo quiere Bea');
  assert.equal(waiting([{ name: 'Ana', is_me: true }, { name: 'Bea', is_me: false }]), 'Lo quieren tú y Bea');
});
