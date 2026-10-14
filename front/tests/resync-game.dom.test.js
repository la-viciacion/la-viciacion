import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { closeAllModals } from '../js/ui/modal.js';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { resyncGame, rawgLine, hltbLine } = await import('../js/pages/admin/resync.js');

afterEach(() => closeAllModals());

const GAME = { id: 'g1', name: 'Path of Exile 2' };
const click = (selector) => document.querySelector(selector).click();

test('it asks first and does nothing when cancelled', async () => {
  const calls = installApi({});
  const done = resyncGame(GAME, { reload: () => {} });
  await settle();
  assert.match(document.body.textContent, /sustituyen/);
  click('[data-close]');
  await done;
  assert.equal(calls.length, 0);
});

test('it shows what each source did and reloads the list on close', async () => {
  let reloaded = 0;
  const calls = installApi({
    'POST /manage/games/g1/resync': { rawg: { status: 'updated', changed: ['release_date', 'image_url'] }, hltb: { status: 'updated', seconds: 72000 } },
  });
  const done = resyncGame(GAME, { reload: () => { reloaded += 1; } });
  await settle();
  click('[data-confirm]');
  await done;
  await settle();
  assert.ok(calls.some((c) => c.method === 'POST' && c.path === '/manage/games/g1/resync'));
  const text = document.body.textContent;
  assert.match(text, /lanzamiento, imagen/);
  assert.match(text, /20 h/);
  click('[data-close]');
  await settle();
  assert.equal(reloaded, 1);
});

test('an ambiguous RAWG match can be resolved from the same dialog', async () => {
  const calls = installApi({
    'POST /manage/games/g1/resync': { rawg: { status: 'ambiguous', candidates: [{ rawg_id: 391403, name: 'Path of Exile 2', released: '2026-12-11', platforms: [] }] }, hltb: { status: 'not_found' } },
    'POST /manage/rawg-sync/apply': { changed: ['rawg_id'], calls: 2 },
  });
  const done = resyncGame(GAME, { reload: () => {} });
  await settle();
  click('[data-confirm]');
  await done;
  await settle();
  click('[data-use="391403"]');
  await settle();
  const apply = calls.find((c) => c.path === '/manage/rawg-sync/apply');
  assert.deepEqual(apply.body, { game_id: 'g1', rawg_id: 391403, overwrite: true });
  assert.match(document.body.textContent, /ID de RAWG/);
});

test('every status has a line', () => {
  for (const status of ['unchanged', 'not_found', 'duplicate', 'error']) assert.ok(rawgLine({ status, other_name: 'X', error: 'e', changed: [] }));
  for (const status of ['unchanged', 'no_time', 'not_found', 'error']) assert.ok(hltbLine({ status, seconds: 3600, error: 'e' }));
});
