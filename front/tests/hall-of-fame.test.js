import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CATEGORIES, HUES, grandChampions, playerHues, seasonsWithChampions, titleRanking } from '../js/lib/hall-of-fame.js';
import { isFameHash } from '../js/lib/season-stats.js';

const by = (id) => CATEGORIES.find((c) => c.id === id);

test('each category writes its figure the way the rankings do', () => {
  assert.equal(by('hours').text(5400), '1 h 30 min');
  assert.equal(by('days').text(1), '1 día');
  assert.equal(by('streak').text(12), '12 días');
  assert.equal(by('completed').text(3), '3');
  assert.deepEqual(CATEGORIES.map((c) => c.id), ['hours', 'days', 'games', 'completed', 'achievements', 'streak']);
  assert.ok(CATEGORIES.every((c) => !c.short.includes(' '))); // one word, so a cell label never takes two lines
});

test('a season in which nobody won anything is left out, and a missing answer is empty', () => {
  const answer = {
    seasons: [
      { season: 2025, champions: { hours: [{ user_id: 1, name: 'Ana', value: 60 }], days: [] } },
      { season: 2024, champions: { hours: [], days: [] } },
    ],
    titles: [{ user_id: 1, name: 'Ana', titles: 1 }],
  };
  assert.deepEqual(seasonsWithChampions(answer).map((s) => s.season), [2025]);
  assert.deepEqual(titleRanking(answer).map((t) => t.name), ['Ana']);
  assert.deepEqual(seasonsWithChampions(null), []);
  assert.deepEqual(titleRanking(undefined), []);
});

test('the address of the hall of fame', () => {
  assert.equal(isFameHash('#/season/fame'), true);
  assert.equal(isFameHash('#/season/fame/'), true);
  assert.equal(isFameHash('#/season/2025'), false);
  assert.equal(isFameHash(undefined), false);
});

const w = (user_id, name, value = 1) => ({ user_id, name, value });
const ANSWER = {
  seasons: [
    { season: 2025, champions: { hours: [w(1, 'Ana')], days: [w(1, 'Ana')], games: [w(2, 'Bob')], completed: [], achievements: [], streak: [w(1, 'Ana'), w(2, 'Bob')] } },
    { season: 2024, champions: { hours: [w(2, 'Bob')], days: [], games: [], completed: [w(2, 'Bob')], achievements: [], streak: [] } },
  ],
  titles: [{ user_id: 2, name: 'Bob', titles: 4 }, { user_id: 1, name: 'Ana', titles: 3 }],
};

test('the grand champion of a season is who won most categories, both on a tie, and none when nobody won', () => {
  assert.deepEqual(grandChampions(ANSWER.seasons[0]), { winners: [{ user_id: 1, name: 'Ana', wins: 3 }], wins: 3, decided: 4 });
  const tied = grandChampions({ champions: { hours: [w(1, 'Ana')], days: [w(2, 'Bob')] } });
  assert.deepEqual(tied.winners.map((x) => x.name), ['Ana', 'Bob']);
  assert.equal(tied.decided, 2);
  assert.deepEqual(grandChampions({ champions: { hours: [] } }), { winners: [], wins: 0, decided: 0 });
  assert.deepEqual(grandChampions({}), { winners: [], wins: 0, decided: 0 });
});

test('each player with titles has a colour by their place in the ranking, starting over past the last one', () => {
  assert.deepEqual([...playerHues(ANSWER)], [[2, 0], [1, 1]]);
  const many = { titles: Array.from({ length: HUES + 1 }, (_, i) => ({ user_id: i + 1, name: `P${i}`, titles: 1 })) };
  assert.equal(playerHues(many).get(HUES + 1), 0);
  assert.equal(playerHues(null).size, 0);
});
