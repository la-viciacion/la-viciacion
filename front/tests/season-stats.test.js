import assert from 'node:assert/strict';
import { test } from 'node:test';
import { RANKINGS, barWidths, podiumOrder, positions, rankingsPath, ringPercent, rowsOf } from '../js/lib/season-stats.js';

const by = (id) => RANKINGS.find((r) => r.id === id);

test('it asks for every ranking of the active players in one request, with the names the API knows', () => {
  assert.equal(RANKINGS.length, 9);
  assert.match(rankingsPath(), /^\/statistics\/rankings\?only_active=true&ranking=user_hours,user_days,.*,games_most_played$/);
});

test('each ranking writes its value the way the bot does', () => {
  assert.equal(by('hours').text({ played_time: 5400 }), '1 h 30 min');
  assert.equal(by('days').text({ played_days: 1 }), '1 día');
  assert.equal(by('ratio').text({ ratio: 0.456 }), '46 %');
});

test('rowsOf takes the data of a ranking and tolerates a missing or odd answer', () => {
  const answer = [{ type: 'user_days', data: [{ name: 'Ana', played_days: 3 }] }, { type: 'user_hours', data: { message: 'x' } }];
  assert.deepEqual(rowsOf(answer, by('days')), [{ name: 'Ana', played_days: 3 }]);
  assert.deepEqual(rowsOf(answer, by('hours')), []);
  assert.deepEqual(rowsOf(null, by('hours')), []);
});

test('the longest bar is full and the others go in proportion', () => {
  assert.deepEqual(barWidths([{ played_days: 8 }, { played_days: 2 }], by('days')), [100, 25]);
  assert.deepEqual(barWidths([], by('days')), []);
});

test('players with the same value share the place', () => {
  const rows = [{ played_days: 5 }, { played_days: 3 }, { played_days: 3 }, { played_days: 1 }];
  assert.deepEqual(positions(rows, by('days')), [1, 2, 2, 4]);
});

test('the podium puts the second at the left of the first, and has fewer steps with fewer rows', () => {
  assert.deepEqual(podiumOrder([1, 2, 3, 4]), [1, 0, 2]);
  assert.deepEqual(podiumOrder([1, 2]), [1, 0]);
  assert.deepEqual(podiumOrder([1]), [0]);
});

test('a ring never goes past the circle', () => {
  assert.equal(ringPercent(0.456), 46);
  assert.equal(ringPercent(1.4), 100);
  assert.equal(ringPercent(-1), 0);
});

test('every ranking has a way of being drawn the page knows', () => {
  assert.ok(RANKINGS.every((r) => ['bars', 'covers', 'podium', 'rings', 'tiles'].includes(r.view)));
});
