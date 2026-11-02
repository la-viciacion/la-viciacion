import assert from 'node:assert/strict';
import { afterEach, mock, test } from 'node:test';
import { closeAllModals } from '../js/ui/modal.js';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
const { batchOf, igdbSyncFlow, minutesLeft } = await import('../js/pages/admin/igdb-sync.js');

afterEach(() => {
  closeAllModals();
  mock.timers.reset();
});

const status = (extra) => ({
  state: 'running', total: 50, processed: 3, current: 'Game', linked: 2, filled: 0, ambiguous: [], duplicates: [], not_found: [], errors: [], stop_reason: null, ...extra,
});
const estimate = { total_games: 528, pending_games: 400, games: 50, estimated_seconds: 75 };

test('the batch size is empty for all the games, or a whole number from one', () => {
  assert.deepEqual(batchOf(''), {});
  assert.deepEqual(batchOf('50'), { max_games: 50 });
  assert.equal(batchOf('0'), null);
  assert.equal(batchOf('2.5'), null);
  assert.equal(batchOf('abc'), null);
});

test('the time left follows the pace seen since the first poll', () => {
  assert.equal(minutesLeft({ at: 0, done: 0 }, { processed: 1, total: 50 }, 5000), null);
  assert.equal(minutesLeft({ at: 0, done: 0 }, { processed: 10, total: 50 }, 20000), 2);
});

test('the admin sizes the batch, sees the figures for it and starts it', async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  const calls = installApi({
    'GET /manage/igdb-sync/status': () => (calls.some((c) => c.method === 'POST') ? status() : { state: 'idle' }),
    'GET /manage/igdb-sync/estimate': estimate,
    'POST /manage/igdb-sync/start': json(status(), 202),
  });
  await igdbSyncFlow({ onDone: () => {} });
  await settle();
  assert.ok(calls.some((c) => c.path === '/manage/igdb-sync/estimate?max_games=50'));
  const form = document.querySelector('form.adm-form');
  form.elements.max.value = '20';
  form.elements.max.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  assert.ok(calls.some((c) => c.path === '/manage/igdb-sync/estimate?max_games=20'));
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body, { max_games: 20 });
  assert.equal(text('.adm-progress-txt')[0], '3 / 50 juegos · Game');
});

test('a doubtful game is linked from its candidates in the list', async () => {
  const doubtful = { game_id: 'fear', name: 'Fear', candidates: [{ igdb_id: 30, name: 'Layers of Fear', year: 2016, platforms: ['PC'] }] };
  const calls = installApi({
    'GET /manage/igdb-sync/status': status({ state: 'finished', stop_reason: 'completed', processed: 50, ambiguous: [doubtful] }),
    'POST /manage/igdb-sync/apply': { linked: true },
  });
  await igdbSyncFlow({ onDone: () => {} });
  await settle();
  const button = document.querySelector('[data-use="30"]');
  assert.equal(button.textContent, 'Layers of Fear (2016)');
  button.click();
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body, { game_id: 'fear', igdb_id: 30 });
  assert.match(text('.adm-amb')[0], /Fear enlazado/);
});
