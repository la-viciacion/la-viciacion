import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
window.location.hash = '#/admin/challenges';
globalThis.location = window.location;
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
const admin = await import('../js/pages/admin/index.js');
const { closeAllModals } = await import('../js/ui/modal.js');

const challenge = { id: 1, title: 'Juego del mes: Hades', label: 'Reto de juego', scope: 'group', owner: null, starts_on: '2026-11-01', ends_on: '2026-11-30', status: 'active', players: 3, done_players: 1, participation: 'auto', total_done: false, created_by: 'root' };
const schedule = { id: 4, label: 'Terror cada mes', kind: 'themed', kind_label: 'Temático', options: { theme: 'Terror' }, games: null, first_month: '2026-12-01', active: true, participation: 'auto', announce: false, last_status: null };

const api = (schedules) => installApi({
  'GET /utils/platforms': [], 'GET /manage/users': { items: [] }, 'GET /manage/achievements': [],
  'GET /manage/challenges': [challenge],
  'GET /manage/challenge-schedules': schedules,
});

test('the schedules are the second table of the challenges, and their buttons act on them', async () => {
  api([schedule]);
  const main = document.getElementById('main');
  await admin.render({ main, user: { id: 1 } });
  await settle();
  assert.equal(document.querySelectorAll('.adm-tab').length, 2); // no tab of their own
  assert.equal(main.querySelectorAll('table').length, 2);
  assert.match(main.textContent, /Se lanzan solos cada mes/);
  assert.match(main.textContent, /Terror cada mes/);
  main.querySelector('[data-c="1"][data-act="edit"]').click();
  await settle();
  assert.equal(document.querySelector('.modal-header h3').textContent, 'Editar · Terror cada mes'); // the schedule's form, not a challenge's
  closeAllModals();
  admin.dispose();
});

test('without schedules there is no second table', async () => {
  api([]);
  const main = document.getElementById('main');
  await admin.render({ main, user: { id: 1 } });
  await settle();
  assert.equal(main.querySelectorAll('table').length, 1);
  assert.doesNotMatch(main.textContent, /Se lanzan solos/);
  admin.dispose();
});
