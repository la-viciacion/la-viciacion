import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
globalThis.location = window.location; // the page reads the address
const page = await import('../js/pages/game/index.js');

const OVERVIEW = {
  game: { id: 'celeste', name: 'Celeste <b>', image_url: null, genres: ['Platformer'], tags: ['Singleplayer', 'platformer', 'Pixel <i>'], dev: 'Maddy', slug: 'celeste', release_date: '2018-01-25', avg_time: 30000 },
  summary: { players: 2, played_seconds: 10800, completed_by: 1, score_count: 2, score_mean: 80 },
  players: [
    { user_id: 2, username: 'bea', name: 'Bea', played_seconds: 7200, sessions: 2, last_played: '2026-03-01T20:00:00', seasons: [2026], completed: true, completions: 1, score: 70, playing: true, is_active: true, is_me: false },
    { user_id: 1, username: 'ana', name: 'Ana', played_seconds: 3600, sessions: 1, last_played: null, seasons: [2026, 2025], completed: false, completions: 0, score: null, playing: false, is_active: false, is_me: true },
  ],
  wished: false,
  wanted_by: [],
};

let calls;
const main = () => document.getElementById('main');

beforeEach(async () => {
  window.location.hash = '#/game/celeste';
  calls = installApi({
    'GET /games/celeste/overview': OVERVIEW,
    'GET /users/photo/': json({ detail: 'no' }, 404),
  });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
});

test('it asks for the game of the address and shows its name as text', () => {
  assert.equal(calls[0].path, '/games/celeste/overview');
  assert.equal(document.querySelector('h1').textContent, 'Celeste <b>');
  assert.equal(document.querySelectorAll('h1 b').length, 0);
});

test('the game links to its RAWG page, in a new tab, when it has a slug', async () => {
  const link = () => main().querySelector('.gm-head a.game-link');
  assert.equal(link().getAttribute('href'), 'https://rawg.io/games/celeste');
  assert.equal(link().getAttribute('target'), '_blank');
});

test('the figures of the group and the players, the most played first, with who plays now', () => {
  assert.deepEqual(text('.pf-stat-label'), ['Jugadores', 'Horas del grupo', 'Completados', 'Nota media (2)']);
  assert.deepEqual(text('.gm-player-name').map((t) => t.split('\n')[0].trim().replace(/\s+/g, ' ')).map((t) => t.split(' ')[0]), ['Bea', 'Ana']);
  assert.ok(document.querySelector('.gm-player .pl-avatar.live'));
  assert.equal(document.querySelectorAll('.gm-player .pl-avatar.live').length, 1);
  assert.match(text('.gm-player.me')[0], /\(tú\)/);
});

test('your own rating can be set from the page', () => {
  assert.equal(document.querySelector('#gmRate').textContent, 'Puntuar');
});

test('a game of your library has no wish button', () => {
  assert.equal(document.querySelector('#gmWish'), null);
});

test('you can wish a game you do not have, and the others who want it are named', async () => {
  const notMine = { ...OVERVIEW, players: OVERVIEW.players.filter((p) => !p.is_me), wanted_by: [{ user_id: 3, username: 'cai', name: 'Cai' }] };
  let overview = notMine;
  const log = installApi({
    'GET /games/celeste/overview': () => overview,
    'PUT /users/ana/wishlist/celeste': () => { overview = { ...notMine, wished: true }; return { game_id: 'celeste', wished: true }; },
    'DELETE /users/ana/wishlist/celeste': () => { overview = notMine; return { game_id: 'celeste', wished: false }; },
    'GET /users/photo/': json({ detail: 'no' }, 404),
  });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
  assert.equal(document.querySelector('#gmRate'), null);
  assert.equal(text('.gm-wanted')[0], 'Lo quiere Cai');
  assert.equal(document.querySelector('#gmWish').textContent, 'Añadir a mi lista');

  document.querySelector('#gmWish').click();
  await settle();
  assert.deepEqual(log.filter((c) => c.method !== 'GET').map((c) => `${c.method} ${c.path}`), ['PUT /users/ana/wishlist/celeste']);
  assert.equal(document.querySelector('#gmWish').textContent, 'Quitar de mi lista');

  document.querySelector('#gmWish').click();
  await settle();
  assert.equal(log.filter((c) => c.method !== 'GET').at(-1).method, 'DELETE');
  assert.equal(document.querySelector('#gmWish').textContent, 'Añadir a mi lista');
});

test('an unknown game says so', async () => {
  installApi({ 'GET /games/celeste/overview': json({ detail: 'Game not exists' }, 404) });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  assert.match(main().textContent, /Este juego no existe/);
});

test('a game that is not a DLC has no mark', () => {
  assert.equal(document.querySelector('.gm-dlc'), null);
});

test('a DLC is marked and links to its base game, escaped; without the base game in the catalogue only the mark', async () => {
  const dlc = (parent) => ({ ...OVERVIEW, game: { ...OVERVIEW.game, is_dlc: true, parent } });
  installApi({ 'GET /games/celeste/overview': dlc({ id: 'base 1', name: 'Base <b>' }), 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  assert.deepEqual(text('.gm-dlc .pf-tag'), ['DLC']);
  const link = document.querySelector('.gm-dlc a');
  assert.equal(link.getAttribute('href'), '#/game/base%201');
  assert.equal(link.textContent, 'Base <b>');
  assert.equal(document.querySelectorAll('.gm-dlc b').length, 0);

  installApi({ 'GET /games/celeste/overview': dlc(null), 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  assert.deepEqual(text('.gm-dlc .pf-tag'), ['DLC']);
  assert.equal(document.querySelector('.gm-dlc a'), null);
});

test('it shows the genres and the tags, without repeating a genre among the tags and escaping them', () => {
  assert.deepEqual(text('.gm-genres:not(.gm-tags) .pf-tag'), ['Platformer']);
  assert.deepEqual(text('.gm-tags .pf-tag'), ['Singleplayer', 'Pixel <i>']);
  assert.equal(document.querySelectorAll('.gm-tags i').length, 0);
});

test('the pace card tells the time of the viewer against the group and HowLongToBeat, and is absent without a pace', async () => {
  installApi({
    'GET /games/celeste/overview': { ...OVERVIEW, pace: { seconds: 3600, completed: false, group_mean: 7200, group_count: 1, group_share: 50, avg_time: 30000, avg_share: 12 } },
    'GET /users/photo/': json({ detail: 'no' }, 404),
  });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
  assert.match(document.querySelector('#gmPace').textContent, /Llevas 1 h de juego\./);
  assert.match(document.querySelector('#gmPace').textContent, /Es el 50 % de lo que ha tardado el resto del grupo/);
  installApi({ 'GET /games/celeste/overview': { ...OVERVIEW, pace: null }, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
  assert.equal(document.querySelector('#gmPace'), null);
});
