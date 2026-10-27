import assert from 'node:assert/strict';
import { test } from 'node:test';
import { STATES, entryPlatforms, entryState, filterEntries, nextUp, openGames, shuffle, unratedGames } from '../js/lib/library-filter.js';

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

test('a row that stands for several platforms matches the filter of any of them', () => {
  const list = [
    e({ id: 1, platform_id: 1, platforms: [{ id: 2, name: 'Switch 2' }, { id: 1, name: 'Switch' }] }),
    e({ id: 2, game_id: 'b', platform_id: 3, platforms: [{ id: 3, name: 'PC' }] }),
    e({ id: 3, game_id: 'c', platform_id: null, platforms: [] }),
  ];
  const ids = (platform) => filterEntries(list, { platform }).map((g) => g.id);
  assert.deepEqual(ids('1'), [1]);
  assert.deepEqual(ids('2'), [1]);
  assert.deepEqual(ids('3'), [2]);
  assert.deepEqual(ids('none'), [3]);
});

test('an item without the list of platforms stands for its own', () => {
  assert.deepEqual(entryPlatforms(e({ platform_name: 'PC' })), [{ id: 1, name: 'PC' }]);
  assert.deepEqual(entryPlatforms(e({ platform_id: null })), []);
});

// ── states and "¿Qué juego sigo?" ──
const NOW = new Date(2026, 9, 27, 12, 0);
const daysAgo = (n) => new Date(NOW.getTime() - n * 86400000).toISOString();
const H = 3600;

test('a pending entry is playing, paused after 30 days without playing or backlog when it was never played', () => {
  assert.equal(entryState(e({ last_played: daysAgo(3) }), NOW), 'playing');
  assert.equal(entryState(e({ last_played: daysAgo(29) }), NOW), 'playing');
  assert.equal(entryState(e({ last_played: daysAgo(31) }), NOW), 'paused');
  assert.equal(entryState(e({ played_time: 0, last_played: null }), NOW), 'backlog');
  assert.equal(entryState(e({ played_time: 600, last_played: null }), NOW), 'playing'); // some time without a date: not backlog
  assert.equal(entryState(e({ completed: true, played_time: 0, last_played: null }), NOW), 'completed');
  assert.equal(entryState(e({ abandoned: true, last_played: daysAgo(90) }), NOW), 'abandoned');
  assert.equal(entryState(e({ complete_blocked: 'closed_season', last_played: daysAgo(90) }), NOW), 'unfinished');
});

test('the filter by state knows the new ones', () => {
  const list = [e({ id: 1, last_played: daysAgo(1) }), e({ id: 2, last_played: daysAgo(40) }), e({ id: 3, played_time: 0, last_played: null })];
  assert.deepEqual(STATES.map(([value]) => value), ['playing', 'paused', 'backlog', 'completed', 'abandoned', 'unfinished']);
  const ids = (state) => filterEntries(list, { state }).map((g) => g.id);
  assert.deepEqual([ids('playing'), ids('paused'), ids('backlog')], [[1], [2], [3]]);
});

test('open games are one per game, with the time of its runs not completed and only if the running season is pending', () => {
  const list = [
    e({ id: 1, game_id: 'a', season: 2026, played_time: 2 * H, avg_time: 10 * H, last_played: daysAgo(2) }),
    e({ id: 2, game_id: 'a', season: 2025, played_time: 3 * H, last_played: daysAgo(300) }), // an earlier run, pending
    e({ id: 3, game_id: 'a', season: 2024, played_time: 99 * H, completed: true }), // a finished run: not counted
    e({ id: 4, game_id: 'b', season: 2026, completed: true }),
    e({ id: 5, game_id: 'c', season: 2025, last_played: daysAgo(400) }), // pending only in a closed season
    e({ id: 6, game_id: 'd', season: 2026, abandoned: true }),
    e({ id: 7, game_id: 'f', season: 2026, complete_blocked: 'completed_in_season' }),
  ];
  const open = openGames(list, NOW);
  assert.deepEqual(open.map((g) => [g.game_id, g.played_time, g.state, g.avg_time]), [['a', 5 * H, 'playing', 10 * H]]);
});

test('"¿Qué juego sigo?" sorts the open games into almost finished, forgotten and short, each in one list', () => {
  const game = (id, over) => e({ id, game_id: `g${id}`, game_name: `G${id}`, season: 2026, avg_time: 10 * H, played_time: 0, last_played: null, ...over });
  const list = [
    game(1, { played_time: 8 * H, last_played: daysAgo(2) }), // 80 %: almost, 2 h left
    game(2, { played_time: 9 * H, last_played: daysAgo(100) }), // 90 % and forgotten: almost goes first
    game(3, { played_time: 7 * H, last_played: daysAgo(1) }), // 70 %: almost, 3 h left
    game(4, { played_time: 2 * H, last_played: daysAgo(90) }), // forgotten
    game(5, { played_time: 4 * H, last_played: daysAgo(70) }), // forgotten, more time put in
    game(6, { avg_time: 3 * H }), // never played, short
    game(7, { avg_time: 4 * H, played_time: 2 * H, last_played: daysAgo(5) }), // 2 h left: short, before the one never played
    game(8, { played_time: 20 * H, last_played: daysAgo(3) }), // 200 %: the average says nothing about it
    game(9, { avg_time: 0, played_time: 1 * H, last_played: daysAgo(2) }), // no average time: nowhere
    game(10, { played_time: 3 * H, last_played: daysAgo(10) }), // 7 h left, played recently: nowhere
  ];
  const { almost, forgotten, short } = nextUp(list, NOW);
  assert.deepEqual(almost.map((g) => g.game_id), ['g2', 'g1', 'g3']);
  assert.deepEqual(forgotten.map((g) => g.game_id), ['g5', 'g4']);
  assert.deepEqual(short.map((g) => [g.game_id, g.left]), [['g7', 2 * H], ['g6', 3 * H]]);
});

test('with nothing to suggest every list is empty', () => {
  assert.deepEqual(nextUp([], NOW), { almost: [], forgotten: [], short: [] });
  assert.deepEqual(nextUp([e({ completed: true })], NOW), { almost: [], forgotten: [], short: [] });
});
