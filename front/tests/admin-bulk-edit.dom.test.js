import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
window.location.hash = '#/admin/timers';
globalThis.location = window.location;
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
const admin = await import('../js/pages/admin/index.js');

const timer = (id) => ({ id, user_id: 1, user: 'ana', game_id: 'doom', game: 'Doom', start_time: '2026-03-01T10:00:00', end_time: '2026-03-01T11:00:00', duration_seconds: 3600, platform: null, season: 2026, is_active: false });
const TOTAL = 60; // two pages of 25 and a third of 10

function setup(patched) {
  return installApi({
    'GET /utils/platforms': [{ id: 'pc', name: 'PC' }, { id: 'switch', name: 'Nintendo Switch' }],
    'GET /manage/users': { items: [] },
    'GET /manage/achievements': [],
    'GET /manage/timers': ({ path }) => {
      const q = new URLSearchParams(path.split('?')[1]);
      const limit = Number(q.get('limit'));
      const offset = Number(q.get('offset'));
      const count = Math.max(0, Math.min(limit, TOTAL - offset));
      return { total: TOTAL, items: Array.from({ length: count }, (_, i) => timer(offset + i + 1)) };
    },
    'PATCH /manage/timers': ({ body }) => {
      patched.push(body);
      return { updated: body.ids.length };
    },
  });
}

const tick = (box, checked = true) => {
  box.checked = checked;
  box.dispatchEvent(new window.Event('change', { bubbles: true }));
};
const bar = () => document.getElementById('admBulkBar').textContent.replace(/\s+/g, ' ').trim();

test('ticking sessions offers a bulk edit that sends the ids and only what was chosen', async () => {
  const patched = [];
  const calls = setup(patched);
  const main = document.getElementById('main');
  await admin.render({ main, user: { id: 1 } });
  await settle();

  assert.equal(bar(), '', 'nothing ticked, nothing offered');
  const boxes = [...document.querySelectorAll('[data-tick]')];
  tick(boxes[0]);
  tick(boxes[2]);
  assert.match(bar(), /Seleccionadas: 2 sesiones/);

  document.querySelector('[data-act="bulk-edit"]').click();
  await settle();
  const form = document.querySelector('.adm-form');
  // nothing chosen yet: it refuses to send an empty change
  form.dispatchEvent(new window.Event('submit', { cancelable: true, bubbles: true }));
  await settle();
  assert.match(document.querySelector('.adm-form .adm-error').textContent, /Elige qué cambiar/);
  assert.equal(patched.length, 0);

  const select = document.getElementById('bulkPlatform');
  select.value = 'switch';
  form.dispatchEvent(new window.Event('submit', { cancelable: true, bubbles: true }));
  await settle();
  await settle();

  assert.deepEqual(patched, [{ ids: [1, 3], platform: 'switch' }]);
  assert.equal(bar(), '', 'the selection is gone once applied');
  assert.ok(calls.filter((c) => c.method === 'GET' && c.path.startsWith('/manage/timers')).length >= 2, 'the table is loaded again');
  admin.dispose();
});

test('"no platform" is sent as null and the box of the header ticks the page', async () => {
  const patched = [];
  setup(patched);
  const main = document.getElementById('main');
  await admin.render({ main, user: { id: 1 } });
  await settle();

  tick(document.getElementById('admBulkAll'));
  assert.match(bar(), /Seleccionadas: 25 sesiones/);
  assert.match(bar(), /Seleccionar las 60 que coinciden/);
  assert.equal(document.querySelectorAll('[data-tick]:checked').length, 25);

  document.querySelector('[data-act="bulk-all"]').click();
  await settle();
  await settle();
  assert.match(bar(), /Seleccionadas: 60 sesiones/);

  document.querySelector('[data-act="bulk-edit"]').click();
  await settle();
  document.getElementById('bulkPlatform').value = '__none';
  document.querySelector('.adm-form').dispatchEvent(new window.Event('submit', { cancelable: true, bubbles: true }));
  await settle();
  await settle();

  assert.equal(patched[0].ids.length, 60);
  assert.equal(patched[0].platform, null);
  assert.ok(!('game_id' in patched[0]), 'the game is not touched');
  admin.dispose();
});

test('the selection survives paging and goes when the filters change', async () => {
  setup([]);
  const main = document.getElementById('main');
  await admin.render({ main, user: { id: 1 } });
  await settle();

  tick(document.querySelector('[data-tick]'));
  document.querySelector('[data-act="next"]').click();
  await settle();
  await settle();
  assert.match(bar(), /Seleccionadas: 1 sesión/);
  assert.equal(document.getElementById('admBulkAll').checked, false);

  const platform = document.querySelector('[data-filter="platform"]');
  platform.value = 'pc';
  platform.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  await settle();
  assert.equal(bar(), '');
  admin.dispose();
});
