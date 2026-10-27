import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/group-library/index.js');

const game = (id, name, extra = {}) => ({ game_id: id, game_name: name, image_url: null, ...extra });
const DATA = {
  summary: { games: 40, players: 4, played_seconds: 360000 },
  hidden_gems: [game('hades', 'Hades <b>', { players: 1, score_mean: 92.5, score_count: 2 })],
  graveyard: [game('doom', 'Doom', { players: 3, abandoned_by: ['Ana', 'Bea'] })],
  rarities: { total: 14, items: [game('limbo', 'Limbo', { owner: 'Cai', seconds: 5400 }), game('inside', 'Inside', { owner: 'Ana', seconds: 0 })] },
  untouched: { total: 1, items: [game('tetris', 'Tetris', { players: 2 })] },
  genres: [{ genre: 'Indie', games: 12, players: 4, seconds: 7200, completed: 3 }, { genre: 'RPG', games: 6, players: 2, seconds: 3600, completed: 1 }],
  platforms: [{ platform: 'pc', platform_name: 'PC', games: 30, players: 4 }, { platform: 'switch', platform_name: 'Switch', games: 10, players: 2 }],
};
const main = () => document.getElementById('main');
const open = async (data = DATA) => {
  installApi({ 'GET /group/library': data });
  await page.render({ main: main() });
  await settle();
};

test('it shows the totals and every list with links to the games, as text', async () => {
  await open();
  assert.deepEqual(text('.pf-stat-value'), ['40', '4', '100 h']);
  assert.deepEqual(text('.section-title'), ['Joyas ocultas', 'El cementerio', 'Rarezas', 'Sin tocar', 'Por género', 'Por plataforma']);
  assert.equal(document.querySelector('.gl-game .game-link').getAttribute('href'), '#/game/hades');
  assert.equal(document.querySelectorAll('.gl-game b').length, 0); // the name is text, never markup
  assert.match(main().textContent, /Hades <b>/);
  assert.match(main().textContent, /1 jugador lo tiene · nota media .* \(2\)/);
  assert.match(main().textContent, /Abandonado por Ana, Bea · lo tienen 3/);
  assert.match(main().textContent, /Solo lo tiene Cai · 1 h 30 min/);
  assert.match(main().textContent, /Solo lo tiene Ana · sin jugar/);
});

test('a list that was cut says how many more there are', async () => {
  await open();
  assert.match(main().textContent, /y 12 más/); // 14 rarities, 2 shown
  assert.doesNotMatch(main().textContent, /y 0 más/);
});

test('the coverage is drawn as bars relative to the largest one', async () => {
  await open();
  assert.deepEqual([...document.querySelectorAll('.gl-bar i')].map((el) => el.getAttribute('style')), ['width:100%', 'width:50%', 'width:100%', 'width:33%']);
  assert.deepEqual(text('.gl-bar-name'), ['Indie', 'RPG', 'PC', 'Switch']);
  assert.match(main().textContent, /30 juegos · 4 jugadores/);
});

test('a group with nothing says so in every list', async () => {
  await open({ summary: { games: 0, players: 0, played_seconds: 0 }, hidden_gems: [], graveyard: [], rarities: { total: 0, items: [] }, untouched: { total: 0, items: [] }, genres: [], platforms: [] });
  assert.match(main().textContent, /Todavía no hay ningún juego poco conocido/);
  assert.match(main().textContent, /Nadie ha abandonado nada/);
  assert.match(main().textContent, /Sin datos de géneros todavía/);
  assert.equal(document.querySelectorAll('.gl-bar').length, 0);
});

test('an error loading is shown', async () => {
  installApi({ 'GET /group/library': () => { throw new Error('Sin conexión'); } });
  await page.render({ main: main() });
  await settle();
  assert.match(main().textContent, /Error cargando la biblioteca del grupo: Sin conexión/);
});

const SECTIONS = ['gems', 'graveyard', 'rarities', 'untouched', 'genres', 'platforms'];
const scrolled = [];
window.Element.prototype.scrollIntoView = function scrollIntoView() { scrolled.push(this.id); };

test('a row of pills reaches every section from the start, each with how many items it has', async () => {
  await open();
  const pills = [...document.querySelectorAll('.gl-pills [data-go]')];
  assert.deepEqual(pills.map((p) => p.dataset.go), SECTIONS);
  assert.deepEqual(pills.map((p) => p.textContent.replace(/\s+/g, ' ').trim()), ['Joyas ocultas 1', 'El cementerio 1', 'Rarezas 14', 'Sin tocar 1', 'Por género 2', 'Por plataforma 2']);
  pills[2].click();
  assert.deepEqual(scrolled.at(-1), 'gl-rarities');
});

test('each section folds on its own, and a pill opens one that was folded', async () => {
  localStorage.removeItem('gl-folded');
  await open();
  const fold = (key) => document.querySelector(`[data-fold="${key}"]`);
  const sectionOf = (key) => document.getElementById(`gl-${key}`);
  assert.deepEqual(SECTIONS.map((key) => fold(key).getAttribute('aria-expanded')), Array(6).fill('true')); // all open at first
  fold('graveyard').click();
  assert.equal(sectionOf('graveyard').classList.contains('folded'), true);
  assert.equal(fold('graveyard').getAttribute('aria-expanded'), 'false');
  assert.equal(sectionOf('gems').classList.contains('folded'), false); // the others are as they were
  document.querySelector('[data-go="graveyard"]').click();
  assert.equal(sectionOf('graveyard').classList.contains('folded'), false);
  assert.equal(fold('graveyard').getAttribute('aria-expanded'), 'true');
  assert.equal(scrolled.at(-1), 'gl-graveyard');
  fold('graveyard').click();
  fold('graveyard').click();
  assert.equal(sectionOf('graveyard').classList.contains('folded'), false); // a second press opens it again
});

test('what was folded is remembered, and a browser without storage still works', async () => {
  localStorage.removeItem('gl-folded');
  await open();
  document.querySelector('[data-fold="genres"]').click();
  assert.deepEqual(JSON.parse(localStorage.getItem('gl-folded')), ['genres']);
  await open();
  assert.equal(document.getElementById('gl-genres').classList.contains('folded'), true);
  const original = localStorage.getItem;
  localStorage.getItem = (key) => { // only what the page remembers is blocked: the session still reads its own
    if (key === 'gl-folded') throw new Error('blocked');
    return original(key);
  };
  await open();
  assert.equal(document.getElementById('gl-genres').classList.contains('folded'), false);
  localStorage.getItem = original;
});

const VALUE = {
  min_contributors: 3, games: 3,
  cheapest: [{ game_id: 'hades', game_name: 'Hades', image_url: null, contributors: 4, per_hour_cents: 120 }],
  priciest: [{ game_id: 'doom', game_name: 'Doom', image_url: null, contributors: 3, per_hour_cents: 950 }],
};
const openWithValue = async (value) => {
  installApi({ 'GET /group/library': DATA, 'GET /group/value': value });
  await page.render({ main: main() });
  await settle();
};

test('the cost per hour of the group is a section with its pill, never with a player or a price', async () => {
  localStorage.removeItem('gl-folded');
  await openWithValue(VALUE);
  assert.ok(document.querySelector('.gl-pills [data-go="value"]'));
  assert.deepEqual(text('#gl-value .game-link'), ['Hades', 'Doom']);
  assert.match(document.querySelector('#gl-value').textContent.replace(/\u00a0/g, ' '), /1,20 €\/h · 4 jugadores/);
  assert.match(document.querySelector('#gl-value').textContent, /al menos 3 jugadores con precio/);
  assert.match(document.querySelector('#gl-value').textContent.replace(/\u00a0/g, ' '), /9,50 €\/h · 3 jugadores/);
});

test('with no game that enough players priced the section says so, and without the data there is no section', async () => {
  await openWithValue({ min_contributors: 3, games: 0, cheapest: [], priciest: [] });
  assert.match(document.querySelector('#gl-value').textContent, /Todavía ningún juego tiene precio de 3 jugadores o más/);
  installApi({ 'GET /group/library': DATA, 'GET /group/value': () => { throw new Error('boom'); } });
  await page.render({ main: main() });
  await settle();
  assert.equal(document.querySelector('#gl-value'), null);
  assert.equal(document.querySelector('.gl-pills [data-go="value"]'), null);
  assert.deepEqual(text('.pf-stat-value'), ['40', '4', '100 h']); // the rest of the page is as it was
});
