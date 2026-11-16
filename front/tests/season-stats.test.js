import assert from 'node:assert/strict';
import { test } from 'node:test';
import { RANKINGS, barWidths, podiumOrder, positions, participantsOf, rankingsOf, rankingsPath, ringPercent, rowsOf, seasonFromHash, TOTAL } from '../js/lib/season-stats.js';
import { current } from '../js/lib/seasons.js';

const by = (id) => RANKINGS.find((r) => r.id === id);

test('it asks for every ranking of the active players in one request, with the names the API knows', () => {
  assert.equal(RANKINGS.length, 11); // the two of the cost per hour are only asked for in the Total
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

test('the Total adds every season together: season 0, everybody who took part, and no current streak', () => {
  const now = new Date(2026, 5, 1);
  assert.equal(seasonFromHash('#/season/total', now), TOTAL);
  assert.equal(seasonFromHash('#/season/total/', now), TOTAL);
  assert.ok(rankingsPath(TOTAL).startsWith('/statistics/rankings?only_active=false&season=0&ranking='));
  assert.ok(!rankingsPath(TOTAL).includes('user_current_streak'));
  assert.equal(rankingsOf(TOTAL).length, 10); // and the two of the cost per hour, which only the Total has
});

test('the rankings that count days explain what a day is, and no other one does', () => {
  assert.deepEqual(RANKINGS.filter((r) => r.info).map((r) => r.id), ['days', 'best-streak', 'current-streak']);
  assert.match(by('days').info, /10 minutos/);
});

test('the cost per hour of the games is only in the Total, the cheapest first, and the cheapest has the full bar', () => {
  assert.ok(!rankingsOf(current()).some((r) => r.total) && !rankingsOf(current() - 1).some((r) => r.total));
  assert.deepEqual(rankingsOf(TOTAL).filter((r) => r.total).map((r) => r.id), ['cheapest', 'priciest']);
  assert.match(rankingsPath(TOTAL), /games_value_cheapest,games_value_priciest/);
  const rows = [
    { game_id: 'b', name: 'Zelda', per_hour_cents: 200, contributors: 3 },
    { game_id: 'a', name: 'Alan Wake', per_hour_cents: 200, contributors: 5 },
    { game_id: 'c', name: 'Celeste', per_hour_cents: 100, contributors: 3 },
  ];
  const answer = [{ type: 'games_value_cheapest', data: rows }, { type: 'games_value_priciest', data: rows }];
  assert.deepEqual(rowsOf(answer, by('cheapest')).map((r) => r.name), ['Celeste', 'Alan Wake', 'Zelda']); // a tie: more players first
  assert.deepEqual(rowsOf(answer, by('priciest')).map((r) => r.name), ['Alan Wake', 'Zelda', 'Celeste']);
  assert.deepEqual(barWidths(rowsOf(answer, by('cheapest')), by('cheapest')), [100, 50, 50]);
  assert.match(by('cheapest').text(rows[0]), /^2,00\s€\/h · 3 jug\.$/);
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

test('nobody shares a place', () => {
  assert.deepEqual(positions([{}, {}, {}, {}]), [1, 2, 3, 4]);
});

test('a tie is broken by the other rankings, in order, and what is still tied goes alphabetically', () => {
  const answer = [
    { type: 'user_days', data: [{ user_id: 1, name: 'Zoe', played_days: 5 }, { user_id: 2, name: 'Ana', played_days: 5 }, { user_id: 3, name: 'Bea', played_days: 5 }, { user_id: 4, name: 'Dan', played_days: 5 }, { user_id: 5, name: 'Eva', played_days: 9 }] },
    { type: 'user_hours', data: [{ user_id: 1, played_time: 7200 }, { user_id: 2, played_time: 3600 }, { user_id: 3, played_time: 3600 }, { user_id: 4, played_time: 3600 }, { user_id: 5, played_time: 0 }] },
    { type: 'user_played_games', data: [{ user_id: 2, played_games: 1 }, { user_id: 3, played_games: 4 }, { user_id: 4, played_games: 4 }] },
  ];
  // Eva has more days; then the hours (Zoe); then the games (Bea and Dan over Ana); Bea and Dan are alike in everything: alphabetical
  assert.deepEqual(rowsOf(answer, by('days')).map((r) => r.name), ['Eva', 'Zoe', 'Bea', 'Dan', 'Ana']);
});

test('the games with the same time: the one played later first, and alphabetically if even that is the same', () => {
  const answer = [{ type: 'games_most_played', data: [
    { game_id: 'b', name: 'Zelda', played_time: 5, last_played: '2026-03-01T10:00:00' },
    { game_id: 'a', name: 'Alan Wake', played_time: 5, last_played: '2026-02-01T10:00:00' },
    { game_id: 'c', name: 'Braid', played_time: 5, last_played: '2026-02-01T10:00:00' },
    { game_id: 'd', name: 'Celeste', played_time: 9, last_played: '2025-01-01T10:00:00' },
  ] }];
  assert.deepEqual(rowsOf(answer, by('most-played')).map((r) => r.name), ['Celeste', 'Zelda', 'Alan Wake', 'Braid']);
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
