import assert from 'node:assert/strict';
import { test } from 'node:test';
import { entryState, filterEntries, shuffle, unratedGames } from '../js/lib/library-filter.js';

const e = (over) => ({ id: 1, game_id: 'a', game_name: 'Celeste', season: 2026, platform_id: 1, score: null, completed: false, abandoned: false, complete_blocked: null, played_time: 60, ...over });

test('an entry is completed, abandoned, unfinished (closed season) or playing', () => {
  assert.equal(entryState(e({ completed: true, abandoned: true })), 'completed');
  assert.equal(entryState(e({ abandoned: true })), 'abandoned');
  assert.equal(entryState(e({ complete_blocked: 'closed_season' })), 'unfinished');
  assert.equal(entryState(e({ complete_blocked: 'completed_in_season' })), 'playing');
});

test('filters combine, search ignores case and accents, and the order is kept', () => {
  const list = [
    e({ id: 1, game_name: 'Pokémon', score: 90 }),
    e({ id: 2, game_id: 'b', game_name: 'Hades', season: 2025, completed: true, platform_id: null }),
    e({ id: 3, game_id: 'c', game_name: 'Poképark', platform_id: 2 }),
  ];
  const ids = (filters) => filterEntries(list, filters).map((g) => g.id);
  assert.deepEqual(ids({}), [1, 2, 3]);
  assert.deepEqual(ids({ q: 'POKEM' }), [1]);
  assert.deepEqual(ids({ season: '2025' }), [2]);
  assert.deepEqual(ids({ state: 'completed' }), [2]);
  assert.deepEqual(ids({ rated: 'yes' }), [1]);
  assert.deepEqual(ids({ rated: 'no' }), [2, 3]);
  assert.deepEqual(ids({ platform: 'none' }), [2]);
  assert.deepEqual(ids({ platform: '2', rated: 'no' }), [3]);
});

test('unrated games: one per game, with the time of all its entries, none of the rated ones', () => {
  const list = [
    e({ id: 1, played_time: 100 }),
    e({ id: 2, season: 2025, played_time: 50 }),
    e({ id: 3, game_id: 'b', score: 70 }),
    e({ id: 4, game_id: 'c', game_name: 'Hades', played_time: 5 }),
  ];
  assert.deepEqual(unratedGames(list).map((g) => [g.game_id, g.played_time]), [['a', 150], ['c', 5]]);
});

test('shuffle keeps every item and does not touch the original', () => {
  const list = [1, 2, 3, 4, 5];
  const out = shuffle(list, () => 0);
  assert.deepEqual([...out].sort(), list);
  assert.deepEqual(list, [1, 2, 3, 4, 5]);
  assert.notDeepEqual(out, list);
});
