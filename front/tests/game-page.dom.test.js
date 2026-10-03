import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
globalThis.location = window.location; // the page reads the address
const page = await import('../js/pages/game/index.js');

const OVERVIEW = {
  game: { id: 'celeste', name: 'Celeste <b>', image_url: null, genres: ['Platformer'], dev: 'Maddy', release_date: '2018-01-25', avg_time: 30000 },
  summary: { players: 2, played_seconds: 10800, completed_by: 1, score_count: 2, score_mean: 80 },
  players: [
    { user_id: 2, username: 'bea', name: 'Bea', played_seconds: 7200, sessions: 2, last_played: '2026-03-01T20:00:00', seasons: [2026], completed: true, completions: 1, score: 70, playing: true, is_me: false },
    { user_id: 1, username: 'ana', name: 'Ana', played_seconds: 3600, sessions: 1, last_played: null, seasons: [2026, 2025], completed: false, completions: 0, score: null, playing: false, is_me: true },
  ],
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

test('an unknown game says so', async () => {
  installApi({ 'GET /games/celeste/overview': json({ detail: 'Game not exists' }, 404) });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  assert.match(main().textContent, /Este juego no existe/);
});
