import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, settle, text } from './dom.js';

installStorage();
installDom();
const { createLibrary } = await import('../js/pages/profile/library.js');
const { closeAllModals } = await import('../js/ui/modal.js');

afterEach(() => closeAllModals());

const entry = (id, over = {}) => ({
  id, game_id: `g${id}`, game_name: `Juego ${id}`, image_url: null, platform_id: 1, platform_name: 'PC', season: 2026,
  played_time: 3600, completed: false, can_complete: true, complete_blocked: null, abandoned: false, can_abandon: true, score: null, ...over,
});
const ENTRIES = [entry(1, { score: 80 }), entry(2), entry(3, { season: 2025, completed: true, can_complete: false, complete_blocked: 'closed_season' })];
const LIBRARY = { 'GET /users/ana/library': { season: 2026, total: 3, items: ENTRIES } };

async function open(extra = {}) {
  document.body.innerHTML = '<div id="box"></div>';
  const calls = installApi({ ...LIBRARY, ...extra });
  const library = createLibrary(document.querySelector('#box'), { username: 'ana', userId: 1, season: 'all', filterable: true, onChange: () => {} });
  await library.init();
  await settle();
  return calls;
}
const names = () => text('.pf-game-title strong');
const filter = (key, value) => {
  const input = document.querySelector(`[data-filter="${key}"]`);
  input.value = value;
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
};
const submitScore = async (value) => {
  const form = document.querySelector('#randForm');
  form.elements.score.value = value;
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
};

test('it lists every season and asks for the whole library', async () => {
  const calls = await open();
  assert.deepEqual(names(), ['Juego 1', 'Juego 2', 'Juego 3']);
  assert.equal(calls[0].path.includes('season='), false);
});

test('the filters narrow the list and say how many are left', async () => {
  await open();
  filter('state', 'completed');
  assert.deepEqual(names(), ['Juego 3']);
  assert.match(document.querySelector('.pf-lib-list .pf-sub').textContent, /1 de 3 juegos/);
  filter('state', '');
  filter('rated', 'no');
  assert.deepEqual(names(), ['Juego 2', 'Juego 3']);
  filter('q', 'juego 2');
  assert.deepEqual(names(), ['Juego 2']);
});

test('the rows have the buttons of the summary list', async () => {
  await open();
  assert.deepEqual(text('.pf-game[data-id="2"] .pf-label'), ['Sesiones', 'Puntuar', 'Marcar completado', 'Abandonar']);
});

test('a button that asks to confirm names its action, since on a phone only the icon shows', async () => {
  await open();
  const row = '.pf-game[data-id="2"]';
  document.querySelector(`${row} [data-action="complete"]`).click();
  document.querySelector(`${row} [data-action="abandon"]`).click();
  assert.deepEqual(text(`${row} [data-armed] .pf-label`), ['¿Completar?', '¿Abandonar?']);
});

test('the random rating asks for the unrated games, one after another, saving each', async () => {
  const calls = await open({ 'PUT /users/ana/games/g2/score': { score: 70 }, 'PUT /users/ana/games/g3/score': { score: 60 } });
  assert.match(document.querySelector('[data-action="random-rate"]').textContent, /\(2\)/);
  document.querySelector('[data-action="random-rate"]').click();
  const seen = [];
  for (const score of ['70', '60']) {
    seen.push(document.querySelector('.rand-name').textContent);
    await submitScore(score);
  }
  assert.deepEqual(seen.sort(), ['Juego 2', 'Juego 3']);
  assert.equal(calls.filter((c) => c.method === 'PUT').length, 2);
  assert.match(document.querySelector('.rand-done').textContent, /has puntuado 2 juegos/);
});

test('"Omitir" shows another game without rating, and "Dejar de puntuar" closes it', async () => {
  const calls = await open();
  document.querySelector('[data-action="random-rate"]').click();
  const first = document.querySelector('.rand-name').textContent;
  document.querySelector('[data-skip]').click();
  assert.notEqual(document.querySelector('.rand-name').textContent, first);
  document.querySelector('.sess-actions [data-close]').click();
  assert.equal(document.querySelectorAll('.modal-overlay').length, 0);
  assert.equal(calls.filter((c) => c.method === 'PUT').length, 0);
});

test('a rating outside 1-100 is refused', async () => {
  const calls = await open();
  document.querySelector('[data-action="random-rate"]').click();
  await submitScore('150');
  assert.match(document.querySelector('.sess-error').textContent, /entero de 1 a 100/);
  assert.equal(calls.filter((c) => c.method === 'PUT').length, 0);
});

const ago = (days) => new Date(Date.now() - days * 86400000).toISOString();
const nextUpEntries = [
  entry(10, { game_name: 'Casi', played_time: 9 * 3600, avg_time: 10 * 3600, last_played: ago(2) }),
  entry(11, { game_name: 'Olvidado', played_time: 3 * 3600, avg_time: 20 * 3600, last_played: ago(90) }),
  entry(12, { game_name: 'Corto', played_time: 0, avg_time: 2 * 3600, last_played: null }),
  entry(13, { game_name: 'Pausado a medias', played_time: 1 * 3600, avg_time: 30 * 3600, last_played: ago(45) }),
];

test('"¿Qué juego sigo?" suggests the nearly finished, the forgotten and the short games', async () => {
  await open({ 'GET /users/ana/library': { season: new Date().getFullYear(), total: 4, items: nextUpEntries.map((g) => ({ ...g, season: new Date().getFullYear() })) } });
  assert.deepEqual(text('.pf-next-list h3'), ['Casi terminados', 'Olvidados', 'Cortos']);
  assert.deepEqual(text('[data-next="almost"] .game-link'), ['Casi']);
  assert.match(document.querySelector('[data-next="almost"]').textContent, /Llevas .* de unas .* te quedan/);
  assert.deepEqual(text('[data-next="forgotten"] .game-link'), ['Olvidado']);
  assert.deepEqual(text('[data-next="short"] .game-link'), ['Corto']);
  assert.match(document.querySelector('[data-next="short"]').textContent, /Duran unas .* según HowLongToBeat/);
});

test('the new states are tags of the rows and options of the filter', async () => {
  await open({ 'GET /users/ana/library': { season: new Date().getFullYear(), total: 4, items: nextUpEntries.map((g) => ({ ...g, season: new Date().getFullYear() })) } });
  const tag = (name) => text('.pf-game').find((row) => row.includes(name));
  assert.match(tag('Pausado a medias'), /Pausado/);
  assert.match(tag('Corto'), /Pendiente/);
  assert.match(tag('Casi'), /En curso/);
  assert.ok([...document.querySelectorAll('[data-filter="state"] option')].some((o) => o.value === 'backlog' && o.textContent === 'Pendientes'));
  filter('state', 'paused');
  assert.deepEqual(names(), ['Olvidado', 'Pausado a medias']);
});

test('the card is not drawn when there is nothing to suggest, and it is only in the full list', async () => {
  await open();
  assert.equal(document.querySelector('.pf-next'), null);
});

// ── prices ──
const withPlatforms = (g, platforms) => ({ ...g, platforms });
const PRICED = [
  withPlatforms(entry(21, { game_name: 'Hades' }), [{ id: 'pc', name: 'PC', price_cents: 2499 }, { id: 'switch', name: 'Switch', price_cents: null }]),
  withPlatforms(entry(22, { game_name: 'Celeste' }), [{ id: 'pc', name: 'PC', price_cents: null }]),
];
const plain = (t) => t.replace(/\u00a0/g, ' ');

test('a row says what was paid, and the price button opens one box per platform with what is noted', async () => {
  await open({ 'GET /users/ana/library': { season: 2026, total: 2, items: PRICED } });
  assert.match(plain(document.querySelector('.pf-game[data-id="21"] .pf-sub').textContent), /Pagado: 24,99 €/);
  assert.doesNotMatch(document.querySelector('.pf-game[data-id="22"] .pf-sub').textContent, /Pagado/);
  document.querySelector('.pf-game[data-id="21"] [data-action="price"]').click();
  const boxes = [...document.querySelectorAll('.pf-game[data-id="21"] input[data-platform]')];
  assert.deepEqual(boxes.map((b) => [b.dataset.platform, b.value]), [['pc', '24,99'], ['switch', '']]);
  assert.equal(document.querySelector('.pf-game[data-id="21"] [data-action="price"]'), null); // the form replaces the buttons
  document.querySelector('[data-action="cancel-price"]').click();
  assert.equal(document.querySelector('[data-price-form]'), null);
});

test('saving the prices sends only what changed, an empty box takes the price off and the list is refreshed', async () => {
  const calls = await open({
    'GET /users/ana/library': { season: 2026, total: 2, items: PRICED },
    'PUT /users/ana/games/g21/price': { ok: true },
  });
  document.querySelector('.pf-game[data-id="21"] [data-action="price"]').click();
  const [pc, switchBox] = document.querySelectorAll('.pf-game[data-id="21"] input[data-platform]');
  pc.value = ''; // takes the PC price off
  switchBox.value = '39,5';
  document.querySelector('[data-price-form]').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const puts = calls.filter((c) => c.method === 'PUT');
  assert.deepEqual(puts.map((c) => c.body), [{ platform: 'pc', amount: null }, { platform: 'switch', amount: 39.5 }]);
  assert.equal(calls.filter((c) => c.method === 'GET' && c.path.startsWith('/users/ana/library')).length >= 2, true); // reloaded
  assert.match(document.querySelector('.pf-msg').textContent, /Precio guardado/);
});

test('a box that did not change sends nothing, and something that is not a price is refused without asking the API', async () => {
  const calls = await open({ 'GET /users/ana/library': { season: 2026, total: 2, items: PRICED } });
  document.querySelector('.pf-game[data-id="21"] [data-action="price"]').click();
  document.querySelector('[data-price-form]').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(calls.some((c) => c.method === 'PUT'), false);
  assert.match(document.querySelector('.pf-msg').textContent, /Nada que guardar/);
  document.querySelector('.pf-game[data-id="21"] [data-action="price"]').click();
  document.querySelector('.pf-game[data-id="21"] input[data-platform="switch"]').value = 'mucho';
  document.querySelector('[data-price-form]').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(calls.some((c) => c.method === 'PUT'), false);
  assert.match(document.querySelector('.pf-msg').textContent, /número, por ejemplo 29,99/);
});

test('an error of the API stays in the list and the price form stays open', async () => {
  await open({
    'GET /users/ana/library': { season: 2026, total: 2, items: PRICED },
    'PUT /users/ana/games/g21/price': () => { throw new Error('No tienes este juego en esa plataforma'); },
  });
  document.querySelector('.pf-game[data-id="21"] [data-action="price"]').click();
  document.querySelector('.pf-game[data-id="21"] input[data-platform="switch"]').value = '10';
  document.querySelector('[data-price-form]').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.match(document.querySelector('.pf-msg').textContent, /No tienes este juego en esa plataforma/);
  assert.notEqual(document.querySelector('[data-price-form]'), null);
});

test('"Lo que has gastado" shows the totals and the cheapest and dearest per hour, only for a player with prices', async () => {
  const VALUE = {
    spent_cents: 7000, priced_games: 7, counted_games: 6, counted_seconds: 360000, per_hour_cents: 70,
    games: ['A', 'B', 'C', 'D', 'E', 'F'].map((name, i) => ({ game_id: `v${i}`, game_name: name, image_url: null, price_cents: 1000, seconds: 36000, per_hour_cents: 100 + i * 10 })).concat([{ game_id: 'v9', game_name: 'Sin tiempo', image_url: null, price_cents: 500, seconds: 60, per_hour_cents: null }]),
  };
  await open({ 'GET /users/ana/library': { season: 2026, total: 2, items: PRICED }, 'GET /users/ana/value': VALUE });
  const card = document.querySelector('.pf-value');
  assert.match(plain(card.textContent), /Solo lo ves tú/);
  assert.deepEqual(text('.pf-value .pf-stat-value').map(plain), ['70 €', '7', '0,70 €/h']);
  assert.deepEqual(text('.pf-value .pv-list:first-child .game-link'), ['A', 'B', 'C', 'D', 'E']); // the cheapest per hour first
  assert.deepEqual(text('.pf-value .pv-list:last-child .game-link'), ['F', 'E', 'D', 'C', 'B']); // and the dearest
  assert.equal(document.querySelectorAll('.pf-value .game-link').length, 10);
  assert.doesNotMatch(card.textContent, /Sin tiempo/); // too little played: no cost per hour
  await open({ 'GET /users/ana/library': { season: 2026, total: 2, items: PRICED }, 'GET /users/ana/value': { spent_cents: 0, priced_games: 0, counted_games: 0, counted_seconds: 0, per_hour_cents: null, games: [] } });
  assert.equal(document.querySelector('.pf-value'), null);
});
