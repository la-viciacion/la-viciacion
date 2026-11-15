import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { closeAllModals } from '../js/ui/modal.js';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { earlyAccessScanFlow } = await import('../js/pages/admin/early-access-scan.js');

afterEach(() => closeAllModals());

const click = (selector) => document.querySelector(selector).click();

test('it asks first and does nothing when cancelled', async () => {
  const calls = installApi({});
  const done = earlyAccessScanFlow({ onDone: () => assert.fail('nothing was done') });
  await settle();
  assert.match(document.body.textContent, /Solo escribe fechas/);
  click('[data-close]');
  await done;
  assert.equal(calls.length, 0);
});

test('it scans once confirmed, says what it did and reloads the list', async () => {
  let reloaded = 0;
  const calls = installApi({ 'POST /manage/igdb-sync/early-access': { asked: 120, changed: 7, failed: 0 } });
  const done = earlyAccessScanFlow({ onDone: () => { reloaded += 1; } });
  await settle();
  click('[data-confirm]');
  await done;
  await settle();
  assert.ok(calls.some((c) => c.method === 'POST' && c.path === '/manage/igdb-sync/early-access'));
  assert.match(document.body.textContent, /120 consultados, 7 actualizados/);
  assert.equal(reloaded, 1);
});

test('a failure is shown and nothing reloads', async () => {
  installApi({ 'POST /manage/igdb-sync/early-access': json({ detail: 'No hay credenciales de IGDB configuradas' }, 400) });
  const done = earlyAccessScanFlow({ onDone: () => assert.fail('it failed') });
  await settle();
  click('[data-confirm]');
  await done;
  await settle();
  assert.match(document.body.textContent, /No hay credenciales de IGDB/);
});
