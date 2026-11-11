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
  wanted: { total: 3, items: [game('hollow', 'Hollow Knight: Silksong', { wanters: ['Ana', 'Bea'], release_date: '2099-01-02', upcoming: true }), game('dune', 'Dune', { wanters: ['Cai'], release_date: null, upcoming: true }), game('out', 'Out', { wanters: ['Ana'], release_date: '2020-01-01', upcoming: false })] },
  together: { total: 1, items: [game('celeste', 'Celeste', { players: 3, season: 2026, seconds: 7200 })] },
  finished: { total: 2, items: [game('hades', 'Hades', { completed: 3, players: 4, mean_seconds: 36000 }), game('inside', 'Inside', { completed: 2, players: 2, mean_seconds: null })] },
  sagas: { total: 3, items: [{ saga: 'Zelda <i>', games: 4, players: 3, seconds: 7200 }] },
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
  assert.deepEqual(text('.section-title'), ['Joyas ocultas', 'El cementerio', 'Rarezas', 'Los más deseados', 'Lo que une al grupo', 'Terminados por varios', 'Sagas', 'Por género', 'Por plataforma']);
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
  assert.deepEqual([...document.querySelectorAll('#gl-genres .gl-bar i, #gl-platforms .gl-bar i')].map((el) => el.getAttribute('style')), ['width:100%', 'width:50%', 'width:100%', 'width:33%']);
  assert.deepEqual(text('#gl-genres .gl-bar-name, #gl-platforms .gl-bar-name'), ['Indie', 'RPG', 'PC', 'Switch']);
  assert.match(main().textContent, /30 juegos · 4 jugadores/);
});

test('a group with nothing says so in every list', async () => {
  await open({ summary: { games: 0, players: 0, played_seconds: 0 }, hidden_gems: [], graveyard: [], rarities: { total: 0, items: [] }, wanted: { total: 0, items: [] }, together: { total: 0, items: [] }, finished: { total: 0, items: [] }, sagas: { total: 0, items: [] }, genres: [], platforms: [] });
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

const SECTIONS = ['gems', 'graveyard', 'rarities', 'wanted', 'together', 'finished', 'sagas', 'genres', 'platforms'];
const scrolled = [];
window.Element.prototype.scrollIntoView = function scrollIntoView() { scrolled.push(this.id); };

test('a row of pills reaches every section from the start, each with how many items it has', async () => {
  await open();
  const pills = [...document.querySelectorAll('.gl-pills [data-go]')];
  assert.deepEqual(pills.map((p) => p.dataset.go), SECTIONS);
  assert.deepEqual(pills.map((p) => p.textContent.replace(/\s+/g, ' ').trim()), ['Joyas ocultas 1', 'El cementerio 1', 'Rarezas 14', 'Los más deseados 3', 'Lo que une al grupo 1', 'Terminados por varios 2', 'Sagas 3', 'Por género 2', 'Por plataforma 2']);
  pills[2].click();
  assert.deepEqual(scrolled.at(-1), 'gl-rarities');
});

test('each section folds on its own, and a pill opens one that was folded', async () => {
  localStorage.removeItem('gl-folded');
  await open();
  const fold = (key) => document.querySelector(`[data-fold="${key}"]`);
  const sectionOf = (key) => document.getElementById(`gl-${key}`);
  assert.deepEqual(SECTIONS.map((key) => fold(key).getAttribute('aria-expanded')), Array(9).fill('true')); // all open at first
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

test('what the group waits for says who wants each game and when it comes out', async () => {
  await open();
  const rows = text('#gl-wanted .gl-game').map((t) => t.replace(/\s+/g, ' '));
  assert.match(rows[0], /Hollow Knight: SilksongAna, Bea · sale el 2 ene 2099/);
  assert.match(rows[1], /DuneCai · sin fecha de salida/);
  assert.match(rows[2], /OutAna · ya ha salido/);
});

test('together, finished and sagas read as sentences and escape what comes from the data', async () => {
  await open();
  assert.match(text('#gl-together .gl-game')[0].replace(/\s+/g, ' '), /3 jugadores en 2026 · 2 h entre todos/);
  const finished = text('#gl-finished .gl-game').map((t) => t.replace(/\s+/g, ' '));
  assert.match(finished[0], /3 de 4 lo han terminado · de media 10 h/);
  assert.doesNotMatch(finished[1], /de media/); // no sessions: no mean
  assert.match(main().querySelector('#gl-sagas').textContent.replace(/\s+/g, ' '), /Zelda <i> 4 juegos · 3 jugadores · 2 h/);
  assert.equal(main().querySelector('#gl-sagas i:not(.gl-bar i)'), null);
  assert.match(main().querySelector('#gl-sagas').textContent, /y 2 más/);
});

test('the cost per hour is no longer on the page', async () => {
  await open();
  assert.equal(document.querySelector('#gl-value'), null);
  assert.equal(document.querySelector('.gl-pills [data-go="value"]'), null);
});
