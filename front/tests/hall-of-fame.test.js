import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CATEGORIES, seasonsWithChampions, titleRanking, titlesText } from '../js/lib/hall-of-fame.js';
import { isFameHash } from '../js/lib/season-stats.js';

const by = (id) => CATEGORIES.find((c) => c.id === id);

test('each category writes its figure the way the rankings do', () => {
  assert.equal(by('hours').text(5400), '1 h 30 min');
  assert.equal(by('days').text(1), '1 día');
  assert.equal(by('streak').text(12), '12 días');
  assert.equal(by('completed').text(3), '3');
  assert.deepEqual(CATEGORIES.map((c) => c.id), ['hours', 'days', 'games', 'completed', 'achievements', 'streak']);
});

test('titles are counted in singular and plural', () => {
  assert.equal(titlesText(1), '1 título');
  assert.equal(titlesText(4), '4 títulos');
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
