import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, settle, text } from './dom.js';

installStorage();
installDom();
const { openCompletion } = await import('../js/pages/home/completion.js');
const { closeAllModals } = await import('../js/ui/modal.js');

afterEach(() => closeAllModals());

const YEAR = new Date().getFullYear();
const ENTRY = { id: 5, game_id: 'celeste', platform_name: 'PC', season: YEAR, played_time: 3600, completed: false, can_complete: true, complete_blocked: null, score: null };

test('one press of "Marcar completado" completes the game: opening the modal was the question', async () => {
  const calls = installApi({
    'GET /users/ana/library': { season: YEAR, total: 1, items: [ENTRY] },
    'PATCH /users/ana/library/5/completion': { ...ENTRY, completed: true, can_complete: false },
  });
  let changed = 0;
  await openCompletion({ username: 'ana', game: { id: 'celeste', name: 'Celeste' }, onChange: () => { changed++; } });
  await settle();
  assert.deepEqual(text('[data-complete]'), ['Marcar completado']);
  document.querySelector('[data-complete]').click();
  await settle();
  const patches = calls.filter((c) => c.method === 'PATCH');
  assert.equal(patches.length, 1);
  assert.deepEqual(patches[0].body, { completed: true });
  assert.equal(changed, 1);
});

test('the button never asks "¿Seguro?" any more', async () => {
  installApi({ 'GET /users/ana/library': { season: YEAR, total: 1, items: [ENTRY] } });
  await openCompletion({ username: 'ana', game: { id: 'celeste', name: 'Celeste' }, onChange: () => {} });
  await settle();
  assert.doesNotMatch(document.querySelector('.comp-body').textContent, /Seguro/);
});
