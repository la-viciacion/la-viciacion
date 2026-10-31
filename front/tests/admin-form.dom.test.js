import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installDom, installStorage } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { closeAllModals } = await import('../js/ui/modal.js');
const { openForm } = await import('../js/pages/admin/form.js');

afterEach(() => closeAllModals());

const entity = {
  createLabel: 'Nuevo',
  name: (r) => r.title,
  fields: [
    { key: 'title', label: 'Título', type: 'text' },
    { key: 'message', label: 'Mensaje', type: 'textarea', rows: 8 },
  ],
};

test('a textarea field is a multi-line box with the saved text and the rows its definition asks for', () => {
  openForm(entity, { title: 'T', message: 'Línea 1 <b>\nLínea 2' }, null);
  const box = document.getElementById('f_message');
  assert.equal(box.tagName, 'TEXTAREA');
  assert.equal(box.getAttribute('rows'), '8');
  assert.equal(box.value, 'Línea 1 <b>\nLínea 2');
  assert.equal(box.querySelector('b'), null); // text, never markup
  assert.equal(document.getElementById('f_title').tagName, 'INPUT');
});

test('with no rows given it still has a few', () => {
  openForm({ ...entity, fields: [{ key: 'message', label: 'Mensaje', type: 'textarea' }] }, { title: 'T', message: '' }, null);
  assert.equal(document.getElementById('f_message').getAttribute('rows'), '4');
});

test('a month field offers the months after the running one as text values', () => {
  openForm({ createLabel: 'Lanzar', name: (r) => r.title, createFields: [{ key: 'month', label: 'Mes', type: 'month', required: true }] }, null, null);
  const values = [...document.querySelectorAll('#f_month option')].map((o) => o.value);
  const next = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 1);
  assert.equal(values.length, 4);
  assert.equal(values[0], `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`);
  assert.match(values[3], /^\d{4}-\d{2}$/);
});

test('a choice field keeps its value as text', () => {
  openForm({ createLabel: 'Lanzar', name: (r) => r.title, createFields: [] }, null, null, {
    label: 'Lanzar reto temático',
    fields: [{ key: 'mode', label: 'Objetivo', type: 'choice', default: 'complete', options: [['play', 'Jugar'], ['complete', 'Completar']] }],
  });
  assert.equal(document.querySelector('.modal-header h3').textContent, 'Lanzar reto temático');
  assert.equal(document.getElementById('f_mode').value, 'complete'); // the default is the one selected
});

test('what a way to create always sends goes with the form', async () => {
  const sent = [];
  globalThis.fetch = async (url, options) => { sent.push({ url: String(url), body: JSON.parse(options.body) }); return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }); };
  const reload = async () => {};
  openForm({ createLabel: 'x', name: (r) => r.title, endpoint: '/manage/challenges', createFields: [] }, null, { reload }, {
    label: 'Lanzar',
    body: { kind: 'themed' },
    fields: [{ key: 'tag', label: 'Temática', type: 'choice', options: [['Horror', 'Horror (2)']] }],
  });
  document.querySelector('.modal-content form').requestSubmit();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(sent.map((s) => [s.url, s.body]), [['/api/v1/manage/challenges', { tag: 'Horror', kind: 'themed' }]]);
});

test('the games form edits every field of a game, the DLC mark and its base game included', async () => {
  const { ENTITIES } = await import('../js/pages/admin/entities.js');
  const keys = ENTITIES.games.fields.map((f) => f.key);
  assert.deepEqual(keys, ['name', 'dev', 'release_date', 'genres', 'tags', 'avg_time', 'image_url', 'steam_id', 'rawg_id', 'slug', 'is_dlc', 'parent_game_id']);

  const row = { id: 'voh', name: 'Vessel <b>', is_dlc: true, parent_game_id: 'd4', parent_name: 'Diablo <IV>' };
  openForm(ENTITIES.games, row, null);
  assert.equal(document.getElementById('f_is_dlc').checked, true);
  assert.equal(document.getElementById('f_parent_game_id').value, 'd4');
  assert.equal(document.getElementById('f_parent_game_id_name').textContent, 'Diablo <IV>');
  assert.equal(document.querySelectorAll('#f_parent_game_id_name b, #f_parent_game_id_name i').length, 0);
});

test('the base game can be taken off, and saving sends it as empty', async () => {
  const { ENTITIES } = await import('../js/pages/admin/entities.js');
  const sent = [];
  globalThis.fetch = async (url, options) => { sent.push({ url: String(url), method: options.method, body: JSON.parse(options.body) }); return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }); };
  openForm(ENTITIES.games, { id: 'voh', name: 'Vessel', is_dlc: true, parent_game_id: 'd4', parent_name: 'Diablo IV' }, { reload: async () => {} });
  document.querySelector('[data-clearfor="parent_game_id"]').click();
  assert.equal(document.getElementById('f_parent_game_id_name').textContent, 'Ninguno');
  document.querySelector('.modal-content form').requestSubmit();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(sent[0].method, 'PATCH');
  assert.equal(sent[0].url, '/api/v1/manage/games/voh');
  assert.equal(sent[0].body.parent_game_id, null);
  assert.equal(sent[0].body.is_dlc, true); // a DLC without a base game is fine
});

test('a choice field shows the value of the row when editing, and the default only when there is none', () => {
  const choice = { key: 'participation', label: 'Quién', type: 'choice', default: 'auto', options: [['auto', 'Todos'], ['opt_in', 'Voluntario']] };
  openForm({ name: (r) => r.label, fields: [choice] }, { label: 'x', participation: 'opt_in' }, null);
  assert.equal(document.getElementById('f_participation').value, 'opt_in');
  closeAllModals();
  openForm({ name: (r) => r.label, fields: [choice] }, { label: 'x' }, null);
  assert.equal(document.getElementById('f_participation').value, 'auto');
});

test('a games field lists the games of the row, adds one from the search, never twice, removes one and sends the ids', async () => {
  const sent = [];
  globalThis.fetch = async (url, options = {}) => {
    sent.push({ url: String(url), method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined });
    const body = String(url).includes('/manage/games?search=') ? { items: [{ id: 'celeste', name: 'Celeste <i>', image_url: null }] } : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  const games = { key: 'games', label: 'Juegos', type: 'games', required: true };
  openForm({ name: (r) => r.label, endpoint: '/manage/challenge-schedules', fields: [games] }, { id: 4, games: [{ id: 'hades', name: 'Hades' }] }, { reload: async () => {} });
  assert.deepEqual([...document.querySelectorAll('#f_games li span')].map((el) => el.textContent), ['Hades']);

  document.querySelector('[data-gameadd="games"]').click();
  await new Promise((resolve) => setTimeout(resolve, 10));
  const input = document.querySelector('.modal-search-input');
  input.value = 'cel';
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 350));
  document.querySelector('.modal-result-row').click();
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.deepEqual([...document.querySelectorAll('#f_games li')].map((li) => li.dataset.id), ['hades', 'celeste']);
  assert.equal(document.querySelectorAll('#f_games li i').length, 0); // the name is text, never markup

  document.querySelector('#f_games li [data-gameremove]').click(); // takes Hades off
  assert.deepEqual([...document.querySelectorAll('#f_games li')].map((li) => li.dataset.id), ['celeste']);
  document.querySelector('.modal-content form').requestSubmit();
  await new Promise((resolve) => setImmediate(resolve));
  const patch = sent.find((s) => s.method === 'PATCH');
  assert.equal(patch.url, '/api/v1/manage/challenge-schedules/4');
  assert.deepEqual(patch.body, { games: ['celeste'] });
});

test('a list of games that is required cannot be empty', async () => {
  const sent = [];
  globalThis.fetch = async (url) => { sent.push(String(url)); return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }); };
  openForm({ name: (r) => r.label, endpoint: '/x', fields: [{ key: 'games', label: 'Juegos de la rotación', type: 'games', required: true }] }, { id: 1, games: [] }, { reload: async () => {} });
  document.querySelector('.modal-content form').requestSubmit();
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(document.querySelector('.adm-error').textContent, /Falta: Juegos de la rotación/);
  assert.deepEqual(sent, []);
});
