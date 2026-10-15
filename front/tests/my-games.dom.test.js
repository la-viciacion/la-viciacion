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
