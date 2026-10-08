import assert from 'node:assert/strict';
import { afterEach, beforeEach, mock, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom();
const { loadPlatforms } = await import('../js/lib/platforms.js');
const { closeAllModals } = await import('../js/ui/modal.js');
const { initGamePicker, openGamePicker, startTimerFlow } = await import('../js/pages/home/game-picker.js');
const { initTimer } = await import('../js/pages/home/timer.js');

const PLATFORMS = [{ id: 'pc', name: 'PC' }, { id: 'switch', name: 'Nintendo Switch' }];
let calls;
let picked;
let started;

beforeEach(async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  picked = null;
  started = [];
  initGamePicker(7);
  initTimer({ userId: 7, onChange: async () => started.push('changed'), onChoose: () => {} });
  calls = installApi({ 'GET /utils/platforms': PLATFORMS });
  await loadPlatforms();
});

afterEach(() => {
  closeAllModals();
  mock.timers.reset();
});

const type = (selector, value) => {
  const input = document.querySelector(selector);
  input.value = value;
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
};
const search = async (selector, value, delay) => {
  type(selector, value);
  mock.timers.tick(delay);
  await settle();
};
const results = (id) => text(`#${id} .modal-result-name`);

test('the search waits for the typing to stop, and asks at least two characters', async () => {
  openGamePicker((id) => (picked = id));
  assert.equal(document.activeElement, document.querySelector('#gamePickerSearch'));
  type('#gamePickerSearch', 'c');
  mock.timers.tick(250);
  assert.equal(text('#gamePickerResults')[0], 'Escribe al menos 2 caracteres');
  assert.equal(calls.length, 1); // only the platforms of beforeEach

  installApi({ 'GET /games/?name=ce': [{ id: 'celeste', name: 'Celeste', image_url: null }, { id: 'ceres', name: 'Ceres <i>', image_url: 'https://img/c.jpg' }] });
  type('#gamePickerSearch', 'ce');
  mock.timers.tick(100);
  type('#gamePickerSearch', 'ce '); // typing again restarts the wait: nothing has been asked yet
  mock.timers.tick(100);
  assert.equal(document.querySelectorAll('.modal-result-row').length, 0);
  mock.timers.tick(150);
  await settle();
  assert.deepEqual(results('gamePickerResults'), ['Celeste', 'Ceres <i>']);
  assert.equal(document.querySelectorAll('#gamePickerResults i').length, 0);
});

test('choosing a result closes the picker and hands over the id and the name', async () => {
  openGamePicker((id, name) => (picked = [id, name]));
  installApi({ 'GET /games/?name=ce': [{ id: 'celeste', name: 'Celeste', image_url: null }] });
  await search('#gamePickerSearch', 'ce', 250);
  document.querySelector('[data-game-id="celeste"]').click();
  assert.deepEqual(picked, ['celeste', 'Celeste']);
  assert.equal(document.querySelector('.modal-overlay'), null);
});

test('no results and API errors are told in the list', async () => {
  openGamePicker(() => {});
  installApi({ 'GET /games/?name=zz': [] });
  await search('#gamePickerSearch', 'zz', 250);
  assert.equal(text('#gamePickerResults')[0], 'Sin resultados en tu catálogo');
  installApi({ 'GET /games/?name=qq': json({ detail: 'Caído' }, 500) });
  await search('#gamePickerSearch', 'qq', 250);
  assert.equal(text('#gamePickerResults')[0], 'Error buscando: Caído');
});

test('closing the picker cancels the search that was waiting', async () => {
  openGamePicker(() => {});
  calls = installApi({});
  type('#gamePickerSearch', 'ce');
  document.querySelector('.modal-close').click();
  mock.timers.tick(1000);
  await settle();
  assert.equal(calls.length, 0);
});

test('a RAWG game already in the catalogue is used at once', async () => {
  openGamePicker((id, name) => (picked = [id, name]));
  document.querySelector('#modalAddGameBtn').click();
  installApi({ 'GET /games/search-rawg?query=hades': [{ name: 'Hades', rawg_id: 1, released: '2020-09-17', exists_in_db: true, db_game_id: 'hades' }] });
  await search('#addGameSearch', 'hades', 300);
  assert.match(text('#addGameResults .modal-result-name')[0], /Hades \(2020\)\s*Ya en tu catálogo/);
  document.querySelector('.modal-result-row').click();
  assert.deepEqual(picked, ['hades', 'Hades']);
});

test('a new RAWG game is only created after a confirmation, and "Volver" cancels it', async () => {
  openGamePicker((id, name) => (picked = [id, name]));
  document.querySelector('#modalAddGameBtn').click();
  const candidate = { name: 'Tunic', rawg_id: 9, released: '2022-03-16', image_url: 'https://img/t.jpg', genres: ['Action', 'Adventure'], slug: 'tunic', exists_in_db: false };
  calls = installApi({
    'GET /games/search-rawg?query=tunic': [candidate],
    'POST /games/': { id: 'tunic', name: 'Tunic' },
  });
  await search('#addGameSearch', 'tunic', 300);
  document.querySelector('.modal-result-row').click();
  assert.match(text('.modal-confirm-text')[0], /Tunic \(2022\)\s*Este juego no está en tu catálogo/);
  assert.equal(calls.filter((c) => c.method === 'POST').length, 0);

  document.querySelector('[data-back]').click();
  assert.equal(document.querySelectorAll('.modal-result-row').length, 1);

  document.querySelector('.modal-result-row').click();
  document.querySelector('[data-confirm]').click();
  await settle();
  assert.deepEqual(calls.at(-1).body, { name: 'Tunic', rawg_id: 9, release_date: '2022-03-16', image_url: 'https://img/t.jpg', genres: 'Action,Adventure', slug: 'tunic' });
  assert.deepEqual(picked, ['tunic', 'Tunic']);
  assert.equal(document.querySelector('.modal-overlay'), null);
});

test('a failure while adding the game stays in the window', async () => {
  openGamePicker(() => {});
  document.querySelector('#modalAddGameBtn').click();
  installApi({
    'GET /games/search-rawg?query=tunic': [{ name: 'Tunic', rawg_id: 9, exists_in_db: false }],
    'POST /games/': json({ detail: 'Ya existe' }, 409),
  });
  await search('#addGameSearch', 'tunic', 300);
  document.querySelector('.modal-result-row').click();
  document.querySelector('[data-confirm]').click();
  await settle();
  assert.equal(text('#addGameResults')[0], 'Error: Ya existe');
});

test('a game RAWG does not have is created by hand with only the name required', async () => {
  openGamePicker((id, name) => (picked = [id, name]));
  document.querySelector('#modalAddGameBtn').click();
  installApi({ 'GET /games/search-rawg?query=fortune': [] });
  await search('#addGameSearch', 'Fortune', 300);
  document.querySelector('#manualGameBtn').click();
  const form = document.querySelector('.sess-form');
  assert.equal(form.elements.game.value, 'Fortune'); // the typed search is the starting name

  form.elements.game.value = '  ';
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(text('.sess-error')[0], 'Escribe el nombre del juego');

  calls = installApi({ 'POST /games/': { id: 'weave', name: "Fortune's Weave" } });
  form.elements.game.value = " Fortune's Weave ";
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(calls.at(-1).body, { name: "Fortune's Weave", release_date: null, dev: null });
  assert.deepEqual(picked, ['weave', "Fortune's Weave"]);
  assert.equal(document.querySelector('.modal-overlay'), null);
});

test('a failure while creating a game by hand stays in the form, and "Volver" goes back to the search', async () => {
  openGamePicker(() => {});
  document.querySelector('#modalAddGameBtn').click();
  document.querySelector('#manualGameBtn').click();
  installApi({ 'POST /games/': json({ detail: 'Ese juego ya está en el catálogo' }, 400) });
  document.querySelector('.sess-form').elements.game.value = 'Celeste';
  document.querySelector('.sess-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(text('.sess-error')[0], 'Error: Ese juego ya está en el catálogo');
  document.querySelector('[data-back]').click();
  assert.ok(document.querySelector('#addGameSearch'));
});

test('"Nuevo timer" on a game never played asks the platform and starts the timer on it', async () => {
  startTimerFlow();
  installApi({
    'GET /games/?name=ce': [{ id: 'celeste', name: 'Celeste' }],
    'GET /timers/history/7/platforms/celeste': { has_history: false, platforms: [] },
    'POST /timers/start': { id: 1 },
  });
  await search('#gamePickerSearch', 'ce', 250);
  document.querySelector('[data-game-id="celeste"]').click();
  await settle();
  assert.equal(text('.modal-hint')[0], 'Este juego es nuevo para ti. ¿En qué plataforma juegas?');
  assert.deepEqual(text('[data-platform]'), ['PC', 'Nintendo Switch']);
  const requests = installApi({ 'POST /timers/start': { id: 1 } });
  document.querySelector('[data-platform="switch"]').click();
  await settle();
  assert.deepEqual(requests[0].body, { user_id: 7, game_id: 'celeste', platform: 'switch' });
  assert.deepEqual(started, ['changed']);
});

test('on a game played before, the last platform comes first and "Otra plataforma" lists them all', async () => {
  startTimerFlow();
  installApi({
    'GET /games/?name=ce': [{ id: 'celeste', name: 'Celeste' }],
    'GET /timers/history/7/platforms/celeste': { has_history: true, platforms: ['switch'] },
  });
  await search('#gamePickerSearch', 'ce', 250);
  document.querySelector('[data-game-id="celeste"]').click();
  await settle();
  assert.match(text('[data-platform]')[0], /Nintendo Switch\s*Misma que la última vez/);
  assert.equal(document.querySelectorAll('[data-platform]').length, 1);
  document.querySelector('#otherPlatformBtn').click();
  assert.equal(text('.modal-hint')[0], 'Elige la nueva plataforma');
  assert.match(text('[data-platform]')[1], /Nintendo Switch\s*Ya usada/);
  assert.equal(document.querySelectorAll('[data-platform]').length, 2);
});
