import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cumulativeSeries, hourAxis } from '../js/lib/daily.js';

const players = [{ user_id: 1, name: 'Ana' }, { user_id: 2, name: 'Bea' }];
const played = (day, user_id, seconds) => ({ type: 'played', day, user_id, seconds });

test('the running total of each player is filled day by day, also the days nobody played', () => {
  const events = [played('2026-03-03', 2, 600), played('2026-03-01', 1, 3600), played('2026-03-01', 1, 1800)];
  const { days, series } = cumulativeSeries(events, players);
  assert.deepEqual(days, ['2026-03-01', '2026-03-02', '2026-03-03']);
  assert.deepEqual(series.map((s) => [s.name, s.values]), [['Ana', [5400, 5400, 5400]], ['Bea', [0, 0, 600]]]);
});

test('only the played events of the given players count', () => {
  const events = [played('2026-03-01', 1, 60), played('2026-03-01', 9, 9999), { type: 'completed', day: '2026-03-01', user_id: 1 }];
  assert.deepEqual(cumulativeSeries(events, players).series[0].values, [60]);
});

test('a season leaves out the other years, and nobody playing gives nothing', () => {
  const events = [played('2026-01-01', 1, 60), played('2025-12-31', 1, 600)];
  assert.deepEqual(cumulativeSeries(events, players, 2025).series[0].values, [600]);
  assert.deepEqual(cumulativeSeries(events, players, 2026).days, ['2026-01-01']);
  assert.equal(cumulativeSeries(events, players, 2024), null);
  assert.equal(cumulativeSeries([], players), null);
});

test('the days cross months and years', () => {
  const { days } = cumulativeSeries([played('2025-12-30', 1, 1), played('2026-01-02', 1, 1)], players);
  assert.deepEqual(days, ['2025-12-30', '2025-12-31', '2026-01-01', '2026-01-02']);
});

test('the vertical axis goes up in four whole-hour steps', () => {
  assert.deepEqual(hourAxis(0), { top: 4, ticks: [0, 1, 2, 3, 4] });
  assert.deepEqual(hourAxis(3600), { top: 4, ticks: [0, 1, 2, 3, 4] });
  assert.deepEqual(hourAxis(4 * 3600 + 1), { top: 8, ticks: [0, 2, 4, 6, 8] });
  assert.deepEqual(hourAxis(100 * 3600), { top: 100, ticks: [0, 25, 50, 75, 100] });
});
