import assert from 'node:assert/strict';
import { test } from 'node:test';
import { RANKINGS, barWidths, podiumOrder, positions, participantsOf, rankingsOf, rankingsPath, ringPercent, rowsOf, seasonFromHash } from '../js/lib/season-stats.js';
import { current } from '../js/lib/seasons.js';

const by = (id) => RANKINGS.find((r) => r.id === id);

test('it asks for every ranking of the active players in one request, with the names the API knows', () => {
  assert.equal(RANKINGS.length, 9);
  const path = rankingsPath();
  assert.ok(path.startsWith(`/statistics/rankings?only_active=true&season=${current()}&ranking=user_hours,user_days,`));
  assert.ok(path.endsWith(',user_current_streak,games_most_played'));
});

test('an older season has no current streak and is asked for by its year', () => {
  assert.equal(rankingsOf(current()).length, 9);
  assert.equal(rankingsOf(current() - 1).length, 8);
  assert.ok(!rankingsOf(current() - 1).some((r) => r.id === 'current-streak'));
  assert.match(rankingsPath(current() - 1), new RegExp(`season=${current() - 1}&ranking=`));
  assert.ok(rankingsPath(current() - 1).startsWith('/statistics/rankings?only_active=false&')); // everybody who took part, active or not
  assert.ok(rankingsPath().includes('only_active=true&'));
  assert.ok(!rankingsPath(current() - 1).includes('user_current_streak'));
});

test('the address names the season, and the running one is the answer to anything else', () => {
  const now = new Date(2026, 5, 1);
  assert.equal(seasonFromHash('#/season/2024', now), 2024);
  assert.equal(seasonFromHash('#/season/2024/', now), 2024);
  for (const hash of ['#/season', '', undefined, '#/season/2027', '#/season/2022', '#/season/abc', '#/season/20244']) assert.equal(seasonFromHash(hash, now), 2026);
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

test('the players of an older season are the ones with something in any ranking, whatever their state today', () => {
  const answer = [
    { type: 'user_hours', data: [{ user_id: 1, played_time: 600 }, { user_id: 2, played_time: 0 }, { user_id: 3, played_time: 0 }, { user_id: 4, played_time: 0 }] },
    { type: 'user_days', data: [{ user_id: 1, played_days: 1 }, { user_id: 2, played_days: 0 }, { user_id: 3, played_days: 0 }, { user_id: 4, played_days: 0 }] },
    { type: 'achievements', data: [{ user_id: 3, achievements: 2 }, { user_id: 1, achievements: 0 }, { user_id: 2, achievements: 0 }, { user_id: 4, achievements: 0 }] },
    { type: 'games_most_played', data: [{ game_id: 'x', name: 'X', played_time: 900 }] },
  ];
  const players = participantsOf(answer, RANKINGS);
  assert.deepEqual([...players].sort(), [1, 3]); // 2 and 4 have nothing that season
  assert.deepEqual(rowsOf(answer, by('hours'), players).map((r) => r.user_id), [1, 3]); // 3 only earned achievements: in every ranking, with a 0
  assert.deepEqual(rowsOf(answer, by('achievements'), players).map((r) => r.user_id), [3, 1]);
  assert.equal(rowsOf(answer, by('most-played'), players).length, 1); // a game is not a player
  assert.equal(rowsOf(answer, by('hours')).length, 4); // without the set nothing is left out
});
