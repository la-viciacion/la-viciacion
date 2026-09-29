import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatClock, formatDate, formatDuration, formatRelative, formatTimestamp, parseDay, toLocalISO } from '../js/lib/format.js';

test('formatDuration', () => {
  assert.equal(formatDuration(0), '0 s');
  assert.equal(formatDuration(59), '59 s');
  assert.equal(formatDuration(60), '1 min');
  assert.equal(formatDuration(3600), '1 h');
  assert.equal(formatDuration(3725), '1 h 2 min');
  assert.equal(formatDuration(-5), '0 s');
  assert.equal(formatDuration(null), '0 s');
});

test('formatClock', () => {
  assert.equal(formatClock(0), '00:00:00');
  assert.equal(formatClock(3725), '01:02:05');
  assert.equal(formatClock(-3), '00:00:00');
});

test('formatRelative', () => {
  const now = new Date(2026, 8, 29, 12, 0, 0);
  assert.equal(formatRelative(new Date(2026, 8, 29, 8, 0), now), 'Hoy');
  assert.equal(formatRelative(new Date(2026, 8, 28, 23, 0), now), 'Ayer');
  assert.equal(formatRelative(new Date(2026, 8, 26, 10, 0), now), 'Hace 3 días');
});

test('formatTimestamp and toLocalISO', () => {
  assert.equal(formatTimestamp('2026-09-29T13:05:07'), '2026-09-29 13:05');
  assert.equal(formatTimestamp(null), '—');
  assert.equal(toLocalISO(new Date(2026, 8, 9, 3, 4, 5)), '2026-09-09T03:04:05');
});

test('parseDay keeps the calendar day whatever the timezone', () => {
  const d = parseDay('2026-09-29');
  assert.deepEqual([d.getFullYear(), d.getMonth(), d.getDate()], [2026, 8, 29]);
  assert.equal(formatDate(null), '—');
  assert.match(formatDate('2026-01-01'), /1/);
});
