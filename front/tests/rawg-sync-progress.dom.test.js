import assert from 'node:assert/strict';
import { afterEach, mock, test } from 'node:test';
import { closeAllModals } from '../js/ui/modal.js';
import { installApi, installDom, installStorage, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { rawgSyncFlow } = await import('../js/pages/admin/rawg-sync.js');

afterEach(() => {
  closeAllModals();
  mock.timers.reset();
});

const ambiguous = (name) => ({ game_id: name, name, candidates: [{ rawg_id: 7, name: `${name} II`, released: '2020-01-01', platforms: ['PC'] }] });
const status = (extra) => ({
  state: 'running', total: 200, current: 'Game', calls: 0, max_calls: 2000, updated: 0, ambiguous: [], duplicates: [], not_found: [], errors: [], stop_reason: null, ...extra,
});

test('the figures keep moving while the admin has a list of candidates open, and the list is left as it is', async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  installApi({ 'GET /manage/rawg-sync/status': () => {
    const n = Math.max(0, calls++ - 1);
    return status({ processed: 3 + n, calls: 10 + n, ambiguous: Array.from({ length: Math.min(n + 1, 3) }, (_, i) => ambiguous(`Game ${i}`)) });
  } });
  await rawgSyncFlow({ onDone: () => {} });
  await settle();
  const list = document.querySelector('.adm-details');
  list.open = true;
  mock.timers.tick(2000);
  await settle();
  mock.timers.tick(2000);
  await settle();
  assert.equal(text('.adm-progress-txt')[0], '5 / 200 juegos · 12 / 2000 llamadas · Game');
  assert.equal(document.querySelector('.adm-details'), list);
  assert.equal(list.open, true);
  assert.equal(list.querySelectorAll('[data-use]').length, 1); // the candidate button is where the admin left it
  list.open = false;
  mock.timers.tick(2000);
  await settle();
  assert.match(document.querySelector('.adm-details summary').textContent, /\(3\)/);
});
