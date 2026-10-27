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
const COMPARE = {
  player: { id: 2, name: 'Bea' }, affinity: { percent: 60, shared_games: 1, shared_rated: 1 }, counts: { shared: 1, only_mine: 1, only_theirs: 1 },
  shared: [{ game_id: 'celeste', game_name: 'Celeste', image_url: null, mine: { seconds: 7200, completed: true, score: 90 }, theirs: { seconds: 3600, completed: false, score: null } }],
  only_mine: [{ game_id: 'hades', game_name: 'Hades <b>', image_url: null, mine: { seconds: 1800, completed: false, score: null }, theirs: null }],
  only_theirs: [{ game_id: 'doom', game_name: 'Doom', image_url: null, mine: null, theirs: { seconds: 600, completed: false, score: 70 } }],
};
const PROFILE = {
  user: { id: 2, username: 'bea', name: 'Bea' }, season: 2026, seasons: [2026, 2025],
  stats: { played_time: 7200, played_days: 3, played_games: 2, completed_games: 1, current_streak: 2, best_streak: 4, achievements: 1 },
  top_games: [{ game_id: 'hades', game_name: 'Hades', played_time: 7200, score: 90 }],
  achievements: [{ title: 'Madrugador', date: '2026-01-02' }],
  hidden_achievements: 2,
  playing: { game_id: 'hades', game_name: 'Hades' }, is_active: true, is_me: false,
};

const main = () => document.getElementById('main');

test('the players come as cards leading to their page, with the one playing marked', async () => {
  installApi({ 'GET /group/players': LIST, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await players.render({ main: main() });
  await settle();
  assert.deepEqual(text('.pl-card-name'), ['Bea <b>', 'Ana (tú)']);
  document.querySelector('[data-filter="all"]').click();
  assert.deepEqual(text('.pl-card-name'), ['Bea <b>', 'Ana (tú)', 'Old Inactivo']);
  assert.equal(document.querySelectorAll('.pl-card.inactive').length, 1);
  document.querySelector('[data-filter="active"]').click();
  assert.equal(document.querySelectorAll('.pl-card-name b').length, 0);
  assert.equal(document.querySelector('.pl-card').getAttribute('href'), '#/player/2');
  assert.match(text('.pl-card')[0], /Jugando Hades/);
  assert.deepEqual(text('.pl-card:first-child .pl-fig-value'), ['2 h', '3', '1']);
  assert.deepEqual(text('.pl-card:first-child .pl-fig-label'), ['Tiempo', 'Juegos', 'Completado']);
  assert.doesNotMatch(main().textContent, /logro/i);
  assert.match(text('.pl-card')[1], /Todavía no ha jugado/);
  assert.equal(document.querySelectorAll('.pl-card .pl-avatar.live').length, 1);
});

test('only the active players show by default, and the filter adds the rest', async () => {
  installApi({ 'GET /group/players': LIST, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await players.render({ main: main() });
  await settle();
  assert.equal(document.querySelectorAll('.pl-card').length, 2);
  assert.equal(document.querySelector('[data-filter="active"]').getAttribute('aria-pressed'), 'true');
  document.querySelector('[data-filter="all"]').click();
  assert.equal(document.querySelectorAll('.pl-card').length, 3);
  assert.equal(document.querySelector('[data-filter="all"]').getAttribute('aria-pressed'), 'true');
  document.querySelector('[data-filter="active"]').click();
  assert.deepEqual(text('.pl-card-name'), ['Bea <b>', 'Ana (tú)']);
});

test('a player page reuses the summary: figures, most played with ratings, achievements', async () => {
  window.location.hash = '#/player/2';
  const calls = installApi({ 'GET /group/players/2/compare': COMPARE, 'GET /group/players/2': PROFILE, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await player.render({ main: main() });
  await settle();
  assert.equal(calls[0].path, '/group/players/2');
  assert.equal(document.querySelector('h1').textContent, 'Bea');
  assert.match(text('.pf-sub')[0], /@bea/);
  assert.ok(text('.pf-stat-label').includes('Horas'));
  assert.equal(text('.pf-bar-label')[0].includes('Hades'), true);
  assert.equal(document.querySelectorAll('.pf-bar-label .score-badge').length, 1);
  assert.match(main().textContent, /Madrugador/);
  assert.match(main().textContent, /\+2 logros ocultos/);  // counted, never named nor dated
  assert.equal(document.querySelectorAll('.pf-head .pl-avatar.live').length, 1);
  assert.equal(document.querySelector('#pfAvatarInput'), null); // nothing of the owner's tools
});

test('the page of another player shows the affinity, or says there is too little to tell', async () => {
  window.location.hash = '#/player/2';
  const shown = (affinity) => {
    installApi({ 'GET /group/players/2/compare': COMPARE, 'GET /group/players/2': { ...PROFILE, affinity }, 'GET /users/photo/': json({ detail: 'no' }, 404) });
    return player.render({ main: main() }).then(settle).then(() => text('#plAffinity')[0] || null);
  };
  assert.match(await shown({ percent: 72, shared_games: 5, shared_rated: 2 }), /72 %.*5 juegos en común, 2 puntuados por los dos/);
  assert.match(await shown({ percent: 40, shared_games: 3, shared_rated: 0 }), /40 %.*3 juegos en común$/);
  assert.match(await shown({ percent: null, shared_games: 1, shared_rated: 0 }), /pocos datos: 1 juego en común.*al menos 3/);
  assert.equal(await shown(null), null); // your own page has none
});

test('an inactive player is marked on their page', async () => {
  window.location.hash = '#/player/2';
  installApi({ 'GET /group/players/2/compare': COMPARE, 'GET /group/players/2': { ...PROFILE, is_active: false }, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await player.render({ main: main() });
  await settle();
  assert.match(text('.pf-head .pf-sub')[0], /Inactivo/);
});

test('the season pills ask for that season again', async () => {
  window.location.hash = '#/player/2';
  const calls = installApi({ 'GET /group/players/2?season=2025': { ...PROFILE, season: 2025 }, 'GET /group/players/2/compare': COMPARE, 'GET /group/players/2': PROFILE, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await player.render({ main: main() });
  await settle();
  document.querySelector('[data-season="2025"]').click();
  await settle();
  const lastPlayer = () => calls.filter((c) => c.path.startsWith('/group/players/') && !c.path.endsWith('/compare')).at(-1).path;
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

test('the page of another player compares the libraries, and your own page does not', async () => {
  installApi({ 'GET /group/players/2/compare': COMPARE, 'GET /group/players/2': PROFILE, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  window.location.hash = '#/player/2';
  await player.render({ main: main() });
  await settle();
  assert.match(document.querySelector('.lc-counts').textContent, /1 en común · 1 solo tuyos · 1 solo de Bea/);
  assert.deepEqual(text('[data-list="shared"] .game-link'), ['Celeste']);
  assert.match(document.querySelector('[data-list="shared"]').textContent, /Tú: 2 h .* completado/);
  assert.match(document.querySelector('[data-list="shared"]').textContent, /Bea: 1 h/);
  assert.deepEqual(text('[data-list="only_mine"] .game-link'), ['Hades <b>']); // text, never markup
  assert.equal(document.querySelectorAll('[data-list="only_mine"] b').length, 0);
  assert.match(document.querySelector('[data-list="only_theirs"] summary').textContent, /Solo lo tiene Bea/);
  installApi({ 'GET /group/players/2': { ...PROFILE, is_me: true }, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  window.location.hash = '#/player/2';
  await player.render({ main: main() });
  await settle();
  assert.equal(document.querySelector('#plCompare'), null);
});

test('a long list shows a few games and "Mostrar más" the rest', async () => {
  const many = Array.from({ length: 20 }, (_, i) => ({ game_id: `g${i}`, game_name: `Juego ${i}`, image_url: null, mine: { seconds: 60, completed: false, score: null }, theirs: null }));
  installApi({ 'GET /group/players/2/compare': { ...COMPARE, counts: { shared: 0, only_mine: 20, only_theirs: 0 }, shared: [], only_mine: many, only_theirs: [] }, 'GET /group/players/2': PROFILE, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  window.location.hash = '#/player/2';
  await player.render({ main: main() });
  await settle();
  assert.equal(document.querySelectorAll('[data-list="only_mine"] .game-link').length, 8);
  document.querySelector('[data-more="only_mine"]').click();
  assert.equal(document.querySelectorAll('[data-list="only_mine"] .game-link').length, 20);
  assert.equal(document.querySelector('[data-more="only_mine"]'), null);
});

test('the comparison says nothing when it cannot be loaded', async () => {
  installApi({ 'GET /group/players/2/compare': json({ detail: 'x' }, 500), 'GET /group/players/2': PROFILE, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  window.location.hash = '#/player/2';
  await player.render({ main: main() });
  await settle();
  assert.match(document.querySelector('#plCompare').textContent, /Cargando/);
});
