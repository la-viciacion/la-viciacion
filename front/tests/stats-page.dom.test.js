import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const stats = await import('../js/pages/stats/index.js');

const LIST = [
  { user_id: 2, name: 'Bea <b>', is_active: true, is_me: false, played_seconds: 7260, games: 3, completed: 1 },
  { user_id: 1, name: 'Ana', is_active: true, is_me: true, played_seconds: 3600, games: 1, completed: 0 },
  { user_id: 3, name: 'Old', is_active: false, is_me: false, played_seconds: 1800, games: 2, completed: 1 },
];
const profile = (id, name, season = 2026, extra = {}) => ({
  user: { id, username: name.toLowerCase(), name }, season, seasons: [2026, 2025],
  stats: { played_time: 7200, played_days: 3, played_games: 2, completed_games: 1, current_streak: 2, best_streak: 4, achievements: 0 },
  top_games: [{ game_id: 'hades', game_name: 'Hades', played_time: 7200, score: 90 }],
  achievements: [], playing: null, is_active: true, is_me: id === 1, ...extra,
});

const main = () => document.getElementById('main');
const photos = { 'GET /users/photo/': json({ detail: 'no' }, 404) };

test('the dropdown lists the players, with me selected and my figures shown', async () => {
  const calls = installApi({ 'GET /group/players/1': profile(1, 'Ana'), 'GET /group/players': LIST, ...photos });
  await stats.render({ main: main() });
  await settle();
  assert.deepEqual(text('#stPlayer option'), ['Todos los jugadores', 'Bea <b>', 'Ana (tú)', 'Old (inactivo)']);
  assert.equal(document.querySelector('#stPlayer').value, '1');
  assert.equal(document.querySelectorAll('#stPlayer option b').length, 0);
  assert.equal(calls.at(-1).path, '/group/players/1');
  assert.ok(text('.pf-stat-label').includes('Tiempo jugado'));
  assert.match(text('.pf-bar-label')[0], /Hades/);
});

test('choosing another player shows theirs, starting at the running season', async () => {
  const calls = installApi({
    'GET /group/players/2?season=2025': profile(2, 'Bea', 2025), 'GET /group/players/2': profile(2, 'Bea'),
    'GET /group/players/1?season=2025': profile(1, 'Ana', 2025), 'GET /group/players/1': profile(1, 'Ana'),
    'GET /group/players': LIST, ...photos,
  });
  await stats.render({ main: main() });
  await settle();
  document.querySelector('[data-season="2025"]').click();
  await settle();
  assert.equal(calls.at(-1).path, '/group/players/1?season=2025');
  const select = document.querySelector('#stPlayer');
  select.value = '2';
  select.dispatchEvent(new window.Event('change'));
  await settle();
  assert.equal(calls.at(-1).path, '/group/players/2');
  assert.equal(document.querySelector('[data-season="2026"]').getAttribute('aria-pressed'), 'true');
});

const SECONDS = { 2: 7260, 1: 3600 }; // played in the running season by Bea and Ana
const SECONDS_2025 = { 2: 1800, 1: 5400 };
const GAMES = { 2: 2, 1: 5 };
const GAMES_2025 = { 2: 4, 1: 1 };

// every player page answers with the figures of its season; the inactive Old (3) is never asked for
const playerPages = ({ path }) => {
  const [, id, season] = /^\/group\/players\/(\d+)(?:\?season=(\w+))?$/.exec(path);
  const old = season === '2025';
  const base = profile(Number(id), id === '1' ? 'Ana' : 'Bea');
  return { ...base, stats: { ...base.stats, played_time: (old ? SECONDS_2025 : SECONDS)[id], played_games: (old ? GAMES_2025 : GAMES)[id] } };
};

const Y = () => new Date().getFullYear(); // the running season, as the page sees it

// the feed, newest first: the "played" events are what the line chart reads (Old, inactive, must not count)
const FEED = () => [
  { type: 'played', day: `${Y()}-03-02`, user_id: 2, seconds: 3600 },
  { type: 'started', day: `${Y()}-03-02`, user_id: 1 },
  { type: 'played', day: `${Y()}-03-01`, user_id: 1, seconds: 1800 },
  { type: 'played', day: `${Y()}-03-01`, user_id: 3, seconds: 9999 },
  { type: 'played', day: `${Y() - 1}-12-30`, user_id: 1, seconds: 600 },
];

const pickEverybody = async () => {
  const calls = installApi({
    'GET /activity': () => ({ items: FEED(), has_more: false }), 'GET /group/players/': playerPages, 'GET /group/players': LIST, ...photos,
  });
  await stats.render({ main: main() });
  await settle();
  const select = document.querySelector('#stPlayer');
  select.value = 'all';
  select.dispatchEvent(new window.Event('change'));
  await settle();
  return calls;
};

const charts = () => [...document.querySelectorAll('#stData .st-block .pf-card')].map((card) => text('.pf-bar-label', card));
const profileCalls = (calls, count = 2) => calls.filter((c) => c.path.startsWith('/group/players/')).slice(-count).map((c) => c.path).sort();

test('"Todos los jugadores" opens with a bar chart of the hours and another of the games, the most first', async () => {
  const calls = await pickEverybody();
  assert.deepEqual(profileCalls(calls), ['/group/players/1', '/group/players/2']);
  assert.deepEqual(text('#stData .section-title'), [`Horas jugadas en ${Y()}`, `Juegos jugados en ${Y()}`, `Evolución de las horas en ${Y()}`]);
  assert.deepEqual(charts().slice(0, 2), [['Bea <b>2 h 1 min', 'Ana (tú)1 h'], ['Ana (tú)5 juegos', 'Bea <b>2 juegos']]);
  assert.equal(document.querySelectorAll('.pf-bar-label b').length, 0);
  assert.deepEqual([...document.querySelectorAll('.pf-bar > div')].map((bar) => bar.style.width), ['100%', '50%', '100%', '40%']);
  assert.equal(document.querySelector('.pf-stat'), null); // the added-up totals need the Total pill
});

test('the line chart adds the hours of the active players up day by day', async () => {
  await pickEverybody();
  assert.deepEqual(text('.st-line .st-axis').slice(0, 5), ['0 h', '1 h', '2 h', '3 h', '4 h']); // Old's 9999 s would raise it
  assert.equal(document.querySelectorAll('.st-line .st-path').length, 2);
  assert.deepEqual(text('.st-legend .st-key'), ['Bea <b>', 'Ana (tú)']); // the one with more hours first
  assert.equal(document.querySelectorAll('.st-legend b').length, 0);
  assert.equal(document.querySelector('.st-line').getAttribute('role'), 'img');
});

test('the pills of the years and Total ask for the figures of that season', async () => {
  const calls = await pickEverybody();
  assert.equal(document.querySelector(`[data-season="${Y()}"]`).getAttribute('aria-pressed'), 'true');
  assert.deepEqual(text('.pf-season-badge').slice(-2), ['Temporada 2023', 'Total']);
  document.querySelector('[data-season="2025"]').click();
  await settle();
  assert.deepEqual(profileCalls(calls), ['/group/players/1?season=2025', '/group/players/2?season=2025']);
  assert.deepEqual(charts().slice(0, 2), [['Ana (tú)1 h 30 min', 'Bea <b>30 min'], ['Bea <b>4 juegos', 'Ana (tú)1 juego']]);
  assert.match(main().textContent, /Todavía no hay días suficientes/); // a single day is no line
  document.querySelector('[data-season="all"]').click();
  await settle();
  assert.deepEqual(profileCalls(calls), ['/group/players/1?season=all', '/group/players/2?season=all']);
  assert.equal(document.querySelectorAll('.st-line .st-path').length, 2);
  assert.deepEqual(text('.pf-stat-label'), ['Tiempo jugado', 'Juegos jugados (suma)', 'Completados']);
  assert.deepEqual(text('.pf-stat-value'), ['3 h 1 min', '4', '1']);
  assert.equal(calls.filter((c) => c.path.startsWith('/activity')).length, 1); // the feed is read once
});

test('a failing player says so and the dropdown stays', async () => {
  installApi({ 'GET /group/players/1': json({ detail: 'Player not found' }, 404), 'GET /group/players': LIST });
  await stats.render({ main: main() });
  await settle();
  assert.match(main().textContent, /Error cargando las estadísticas/);
  assert.ok(document.querySelector('#stPlayer'));
});

test('without players there is nothing to pick', async () => {
  installApi({ 'GET /group/players': [] });
  await stats.render({ main: main() });
  await settle();
  assert.match(main().textContent, /Todavía no hay jugadores/);
  assert.equal(document.querySelector('#stPlayer'), null);
});
