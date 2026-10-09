import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
globalThis.location = window.location;
const players = await import('../js/pages/players/index.js');
const player = await import('../js/pages/player/index.js');

const LIST = [
  { user_id: 2, username: 'bea', name: 'Bea <b>', played_seconds: 7260, games: 3, completed: 1, achievements: 1, last_played: '2026-03-01T20:00:00',
    playing: { game_id: 'hades', game_name: 'Hades', platform: 'pc' }, is_active: true, is_me: false },
  { user_id: 1, username: 'ana', name: 'Ana', played_seconds: 3600, games: 1, completed: 0, achievements: 2, last_played: null, playing: null, is_active: true, is_me: true },
  { user_id: 3, username: 'old', name: 'Old', played_seconds: 0, games: 0, completed: 0, achievements: 0, last_played: null, playing: null, is_active: false, is_me: false },
];
const PROFILE = {
  user: { id: 2, username: 'bea', name: 'Bea' }, season: 2026, seasons: [2026, 2025],
  stats: { played_time: 7200, played_days: 3, played_games: 2, completed_games: 1, current_streak: 2, best_streak: 4, achievements: 1 },
  top_games: [{ game_id: 'hades', game_name: 'Hades', played_time: 7200, score: 90 }],
  achievements: [{ title: 'Madrugador', date: '2026-01-02' }],
  playing: { game_id: 'hades', game_name: 'Hades' }, is_active: true, is_me: false,
};

const main = () => document.getElementById('main');

test('the players come as cards leading to their page, with the one playing marked', async () => {
  installApi({ 'GET /group/players': LIST, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await players.render({ main: main() });
  await settle();
  assert.deepEqual(text('.pl-card-name'), ['Bea <b>', 'Ana (tú)', 'Old Inactivo']);
  assert.equal(document.querySelectorAll('.pl-card.inactive').length, 1);
  assert.equal(document.querySelectorAll('.pl-card-name b').length, 0);
  assert.equal(document.querySelector('.pl-card').getAttribute('href'), '#/player/2');
  assert.match(text('.pl-card')[0], /Jugando Hades/);
  assert.deepEqual(text('.pl-card:first-child .pl-fig-value'), ['2 h', '3', '1']);
  assert.deepEqual(text('.pl-card:first-child .pl-fig-label'), ['Tiempo', 'Juegos', 'Completado']);
  assert.doesNotMatch(main().textContent, /logro/i);
  assert.match(text('.pl-card')[1], /Todavía no ha jugado/);
  assert.equal(document.querySelectorAll('.pl-card .pl-avatar.live').length, 1);
});

test('the filter shows everybody or only the active players', async () => {
  installApi({ 'GET /group/players': LIST, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await players.render({ main: main() });
  await settle();
  assert.equal(document.querySelectorAll('.pl-card').length, 3);
  assert.equal(document.querySelector('[data-filter="all"]').getAttribute('aria-pressed'), 'true');
  document.querySelector('[data-filter="active"]').click();
  assert.deepEqual(text('.pl-card-name'), ['Bea <b>', 'Ana (tú)']);
  assert.equal(document.querySelector('[data-filter="active"]').getAttribute('aria-pressed'), 'true');
  document.querySelector('[data-filter="all"]').click();
  assert.equal(document.querySelectorAll('.pl-card').length, 3);
});

test('a player page reuses the summary: figures, most played with ratings, achievements', async () => {
  window.location.hash = '#/player/2';
  const calls = installApi({ 'GET /group/players/2': PROFILE, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await player.render({ main: main() });
  await settle();
  assert.equal(calls[0].path, '/group/players/2');
  assert.equal(document.querySelector('h1').textContent, 'Bea');
  assert.match(text('.pf-sub')[0], /@bea/);
  assert.ok(text('.pf-stat-label').includes('Tiempo jugado'));
  assert.equal(text('.pf-bar-label')[0].includes('Hades'), true);
  assert.equal(document.querySelectorAll('.pf-bar-label .score-badge').length, 1);
  assert.match(main().textContent, /Madrugador/);
  assert.equal(document.querySelectorAll('.pf-head .pl-avatar.live').length, 1);
  assert.equal(document.querySelector('#pfAvatarInput'), null); // nothing of the owner's tools
});

test('the page of another player shows the affinity, or says there is too little to tell', async () => {
  window.location.hash = '#/player/2';
  const shown = (affinity) => {
    installApi({ 'GET /group/players/2': { ...PROFILE, affinity }, 'GET /users/photo/': json({ detail: 'no' }, 404) });
    return player.render({ main: main() }).then(settle).then(() => text('#plAffinity')[0] || null);
  };
  assert.match(await shown({ percent: 72, shared_games: 5, shared_rated: 2 }), /72 %.*5 juegos en común, 2 puntuados por los dos/);
  assert.match(await shown({ percent: 40, shared_games: 3, shared_rated: 0 }), /40 %.*3 juegos en común$/);
  assert.match(await shown({ percent: null, shared_games: 1, shared_rated: 0 }), /pocos datos: 1 juego en común.*al menos 3/);
  assert.equal(await shown(null), null); // your own page has none
});

test('an inactive player is marked on their page', async () => {
  window.location.hash = '#/player/2';
  installApi({ 'GET /group/players/2': { ...PROFILE, is_active: false }, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await player.render({ main: main() });
  await settle();
  assert.match(text('.pf-head .pf-sub')[0], /Inactivo/);
});

test('the season pills ask for that season again', async () => {
  window.location.hash = '#/player/2';
  const calls = installApi({ 'GET /group/players/2?season=2025': { ...PROFILE, season: 2025 }, 'GET /group/players/2': PROFILE, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await player.render({ main: main() });
  await settle();
  document.querySelector('[data-season="2025"]').click();
  await settle();
  const lastPlayer = () => calls.filter((c) => c.path.startsWith('/group/players/')).at(-1).path;
  assert.equal(lastPlayer(), '/group/players/2?season=2025');
  document.querySelector('[data-season="all"]').click();
  assert.equal(lastPlayer(), '/group/players/2?season=all');
});

test('an unknown player says so', async () => {
  window.location.hash = '#/player/99';
  installApi({ 'GET /group/players/99': json({ detail: 'Player not found' }, 404) });
  await player.render({ main: main() });
  assert.match(main().textContent, /Este jugador no existe/);
});
