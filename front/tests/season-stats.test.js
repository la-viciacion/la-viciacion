import assert from 'node:assert/strict';
import { test } from 'node:test';
import { RANKINGS, barWidths, positions, rankingsPath, rowsOf, visibleRows } from '../js/lib/season-stats.js';

const by = (id) => RANKINGS.find((r) => r.id === id);

test('it asks for every ranking of the active players in one request, with the names the API knows', () => {
  assert.equal(RANKINGS.length, 11);
  assert.match(rankingsPath(), /^\/statistics\/rankings\?only_active=true&ranking=user_hours,user_days,.*,debt,debt_total$/);
});

test('each ranking writes its value the way the bot does', () => {
  assert.equal(by('hours').text({ played_time: 5400 }), '1 h 30 min');
  assert.equal(by('days').text({ played_days: 1 }), '1 día');
  assert.equal(by('ratio').text({ ratio: 0.456 }), '46 %');
  assert.equal(by('debt').text({ debt_time: 7200, games: 2 }), '2 h en 2 juegos');
  assert.equal(by('debt').text({ debt_time: 3600, games: 1 }), '1 h en 1 juego');
});

test('rowsOf takes the data of a ranking and tolerates a missing or odd answer', () => {
  const answer = [{ type: 'user_days', data: [{ name: 'Ana', played_days: 3 }] }, { type: 'debt', data: { message: 'x' } }];
  assert.deepEqual(rowsOf(answer, by('days')), [{ name: 'Ana', played_days: 3 }]);
  assert.deepEqual(rowsOf(answer, by('debt')), []);
  assert.deepEqual(rowsOf(answer, by('hours')), []);
  assert.deepEqual(rowsOf(null, by('hours')), []);
});

test('rows with nothing are left out and the list is cut at the limit', () => {
  const rows = [{ achievements: 3 }, { achievements: 2 }, { achievements: 0 }];
  assert.equal(visibleRows(rows, by('achievements'), 10).length, 2);
  assert.equal(visibleRows(rows, by('achievements'), 1).length, 1);
});

test('the longest bar is full and the others go in proportion', () => {
  assert.deepEqual(barWidths([{ played_days: 8 }, { played_days: 2 }], by('days')), [100, 25]);
  assert.deepEqual(barWidths([], by('days')), []);
});

test('players with the same value share the place', () => {
  const rows = [{ played_days: 5 }, { played_days: 3 }, { played_days: 3 }, { played_days: 1 }];
  assert.deepEqual(positions(rows, by('days')), [1, 2, 2, 4]);
});
