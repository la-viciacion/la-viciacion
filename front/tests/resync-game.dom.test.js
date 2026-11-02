import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { closeAllModals } from '../js/ui/modal.js';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { resyncGame, rawgLine, igdbLine, hltbLine } = await import('../js/pages/admin/resync.js');

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
    'POST /manage/games/g1/resync': { rawg: { status: 'updated', changed: ['release_date', 'image_url'] }, igdb: { status: 'updated', changed: ['themes', 'igdb_id'] }, hltb: { status: 'updated', seconds: 72000 } },
  });
  const done = resyncGame(GAME, { reload: () => { reloaded += 1; } });
  await settle();
  click('[data-confirm]');
  await done;
  await settle();
  assert.ok(calls.some((c) => c.method === 'POST' && c.path === '/manage/games/g1/resync'));
  const text = document.body.textContent;
  assert.match(text, /lanzamiento, imagen/);
  assert.match(text, /temas, ID de IGDB/);
  assert.match(text, /20 h/);
  click('[data-close]');
  await settle();
  assert.equal(reloaded, 1);
});

test('a window is up while the sources are asked and it turns into the results', async () => {
  let answer;
  installApi({ 'POST /manage/games/g1/resync': () => new Promise((resolve) => { answer = resolve; }) });
  const done = resyncGame(GAME, { reload: () => {} });
  await settle();
  click('[data-confirm]');
  await settle();
  assert.match(document.body.textContent, /Resincronizando · Path of Exile 2/);
  assert.ok(document.querySelector('.adm-indeterminate'));
  assert.equal(document.querySelector('.toast'), null); // no banner: the window says it
  answer({ rawg: { status: 'unchanged' }, igdb: { status: 'updated', changed: ['themes'] }, hltb: { status: 'not_found' } });
  await done;
  await settle();
  assert.match(document.body.textContent, /Resincronizado · Path of Exile 2/);
  assert.equal(document.querySelector('.adm-indeterminate'), null);
  assert.match(document.body.textContent, /temas/);
});

test('a failure is told in the same window', async () => {
  installApi({ 'POST /manage/games/g1/resync': json({ detail: 'Fallo de prueba' }, 500) });
  const done = resyncGame(GAME, { reload: () => {} });
  await settle();
  click('[data-confirm]');
  await done;
  await settle();
  assert.match(document.querySelector('.adm-error').textContent, /Fallo de prueba/);
  assert.equal(document.querySelector('.adm-indeterminate'), null);
  assert.ok(document.querySelector('[data-close]'));
});

test('an ambiguous RAWG match can be resolved from the same dialog', async () => {
  const calls = installApi({
    'POST /manage/games/g1/resync': { rawg: { status: 'ambiguous', candidates: [{ rawg_id: 391403, name: 'Path of Exile 2', released: '2026-12-11', platforms: [] }] }, igdb: { status: 'not_found' }, hltb: { status: 'not_found' } },
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

test('an ambiguous IGDB match can be resolved from the same dialog and the RAWG block stays as it was', async () => {
  const calls = installApi({
    'POST /manage/games/g1/resync': {
      rawg: { status: 'not_found' }, hltb: { status: 'not_found' },
      igdb: { status: 'ambiguous', candidates: [{ igdb_id: 7, name: 'Path of Exile 2', year: 2026, platforms: ['PC'] }] },
    },
    'POST /manage/igdb-sync/apply': { linked: true, changed: ['igdb_id', 'themes'] },
  });
  const done = resyncGame(GAME, { reload: () => {} });
  await settle();
  click('[data-confirm]');
  await done;
  await settle();
  click('[data-use-igdb="7"]');
  await settle();
  const apply = calls.find((c) => c.path === '/manage/igdb-sync/apply');
  assert.deepEqual(apply.body, { game_id: 'g1', igdb_id: 7, overwrite: true });
  assert.match(document.body.textContent, /ID de IGDB, temas/);
  assert.match(document.body.textContent, /No lo encuentra en RAWG/);
});

test('every status has a line', () => {
  for (const status of ['unchanged', 'not_found', 'duplicate', 'error']) assert.ok(igdbLine({ status, other_name: 'X', error: 'e', changed: [] }));
  for (const status of ['unchanged', 'not_found', 'duplicate', 'error']) assert.ok(rawgLine({ status, other_name: 'X', error: 'e', changed: [] }));
  for (const status of ['unchanged', 'no_time', 'not_found', 'error']) assert.ok(hltbLine({ status, seconds: 3600, error: 'e' }));
});
