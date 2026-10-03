import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dayLabel, groupByDay } from '../js/lib/activity.js';

const NOW = new Date(2026, 9, 3, 12, 0); // 3 Oct 2026

test('today, yesterday and any other day', () => {
  assert.equal(dayLabel('2026-10-03', NOW), 'Hoy');
  assert.equal(dayLabel('2026-10-02', NOW), 'Ayer');
  assert.match(dayLabel('2026-09-20', NOW), /20/);
  assert.match(dayLabel('2026-09-20', NOW), /2026/);
});

test('yesterday is yesterday across a month boundary', () => {
  assert.equal(dayLabel('2026-09-30', new Date(2026, 9, 1, 8, 0)), 'Ayer');
});

test('events come in runs of the same day, in the order they arrived', () => {
  const events = [{ day: '2026-10-03', n: 1 }, { day: '2026-10-03', n: 2 }, { day: '2026-10-01', n: 3 }];
  assert.deepEqual(groupByDay(events).map((g) => [g.day, g.events.map((e) => e.n)]), [['2026-10-03', [1, 2]], ['2026-10-01', [3]]]);
  assert.deepEqual(groupByDay([]), []);
});
