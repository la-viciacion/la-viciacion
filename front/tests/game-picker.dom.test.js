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

test('an older answer that arrives after a newer one is not drawn', async () => {
  openGamePicker(() => {});
  let answerSlow;
  installApi({ // the longer key first: routes match by prefix
    'GET /games/?name=cel': [{ id: 'celeste', name: 'Celeste', image_url: null }],
    'GET /games/?name=ce': () => new Promise((resolve) => { answerSlow = resolve; }),
  });
  type('#gamePickerSearch', 'ce');
  mock.timers.tick(250);
  await search('#gamePickerSearch', 'cel', 250);
  answerSlow(json([{ id: 'ceres', name: 'Ceres', image_url: null }]));
  await settle();
  assert.deepEqual(results('gamePickerResults'), ['Celeste']);
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

test('a DLC says which game it belongs to, never blocks adding it, and a game of its own says nothing', async () => {
  openGamePicker(() => {});
  document.querySelector('#modalAddGameBtn').click();
  const dlc = { name: 'Vessel of Hatred', rawg_id: 11, exists_in_db: false };
  installApi({
    'GET /games/search-rawg?query=vessel': [dlc, { name: 'Tunic', rawg_id: 9, exists_in_db: false }],
    'GET /games/rawg-parent/11': { rawg_id: 5, name: 'Diablo <IV>', exists_in_db: false },
    'GET /games/rawg-parent/9': null,
  });
  await search('#addGameSearch', 'vessel', 300);
  document.querySelectorAll('.modal-result-row')[0].click();
  await settle();
  assert.equal(text('.modal-dlc-note')[0], 'Es un DLC o expansión de «Diablo <IV>», que se añadirá también al catálogo.');
  assert.equal(document.querySelectorAll('.modal-dlc-note i').length, 0);
  assert.ok(document.querySelector('[data-confirm]'));

  document.querySelector('[data-back]').click();
  document.querySelectorAll('.modal-result-row')[1].click();
  await settle();
  assert.equal(text('.modal-dlc-note')[0] ?? '', '');

  installApi({ 'GET /games/rawg-parent/11': { rawg_id: 5, name: 'Diablo IV', exists_in_db: true, db_game_id: 'd4' } });
  document.querySelector('[data-back]').click();
  document.querySelectorAll('.modal-result-row')[0].click();
  await settle();
  assert.match(text('.modal-dlc-note')[0], /que ya está en el catálogo\.$/);
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

test('a game made by hand can be marked as a DLC, with or without a base game from the catalogue', async () => {
  openGamePicker((id, name) => (picked = [id, name]));
  document.querySelector('#modalAddGameBtn').click();
  document.querySelector('#manualGameBtn').click();
  const form = document.querySelector('.sess-form');
  const submit = async () => {
    form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
    await settle();
  };
  assert.equal(document.querySelector('.dlc-base').hidden, true);

  // a DLC without saying of which game
  form.elements.game.value = 'Expansión suelta';
  form.elements.is_dlc.checked = true;
  form.elements.is_dlc.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(document.querySelector('.dlc-base').hidden, false);
  calls = installApi({ 'POST /games/': { id: 'x', name: 'Expansión suelta' } });
  await submit();
  assert.deepEqual(calls.at(-1).body, { name: 'Expansión suelta', release_date: null, dev: null, is_dlc: true, parent_game_id: null });

  // with a base game picked from the catalogue (escaped), which can be taken off again
  openGamePicker((id, name) => (picked = [id, name]));
  document.querySelector('#modalAddGameBtn').click();
  document.querySelector('#manualGameBtn').click();
  const second = document.querySelector('.sess-form');
  second.elements.game.value = 'Vessel';
  second.elements.is_dlc.checked = true;
  second.elements.is_dlc.dispatchEvent(new window.Event('change', { bubbles: true }));
  installApi({ 'GET /games/?name=dia': [{ id: 'd4', name: 'Diablo <IV>', image_url: null }] });
  await search('#dlcBaseSearch', 'dia', 250);
  assert.deepEqual(text('.dlc-base-results .modal-result-name'), ['Diablo <IV>']);
  document.querySelector('.dlc-base-results .modal-result-row').click();
  assert.equal(text('.dlc-base-chosen .pf-tag')[0], 'Juego base: Diablo <IV>');
  assert.equal(document.querySelectorAll('.dlc-base-chosen i').length, 0);
  assert.equal(document.querySelectorAll('.dlc-base-results .modal-result-row').length, 0);

  document.querySelector('[data-clear]').click();
  assert.equal(document.querySelector('.dlc-base-chosen .pf-tag'), null);
  await search('#dlcBaseSearch', 'dia', 250);
  document.querySelector('.dlc-base-results .modal-result-row').click();
  calls = installApi({ 'POST /games/': { id: 'v', name: 'Vessel' } });
  second.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(calls.at(-1).body, { name: 'Vessel', release_date: null, dev: null, is_dlc: true, parent_game_id: 'd4' });
  assert.deepEqual(picked, ['v', 'Vessel']);
});

test('a game made by hand without the DLC box checked is sent as before', async () => {
  openGamePicker(() => {});
  document.querySelector('#modalAddGameBtn').click();
  document.querySelector('#manualGameBtn').click();
  const form = document.querySelector('.sess-form');
  form.elements.game.value = 'Celeste';
  calls = installApi({ 'POST /games/': { id: 'c', name: 'Celeste' } });
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(calls.at(-1).body, { name: 'Celeste', release_date: null, dev: null });
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
