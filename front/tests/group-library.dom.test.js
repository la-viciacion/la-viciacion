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
