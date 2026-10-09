import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/challenges/index.js');
const history = await import('../js/ui/challenges-history.js');

const main = () => document.getElementById('main');
const ANA = { id: 1, username: 'ana', is_admin: false };
const ROOT = { id: 9, username: 'root', is_admin: true };

const challenge = (extra = {}) => ({
  id: 5, kind: 'game_of_month', label: 'Juego del mes', scope: 'group', title: 'Juego del mes: Hades <b>', status: 'active',
  starts_on: '2026-10-01', ends_on: '2026-10-31', params: { min_hours_each: 5, min_hours_total: 12 },
  game: { id: 'hades', name: 'Hades', image_url: null }, taking_part: true, can_opt_out: true,
  progress: {
    players: [
      { user_id: 1, name: 'Ana', seconds: 25200, target_seconds: 18000, done: true },
      { user_id: 2, name: 'Bea', seconds: 7200, target_seconds: 18000, done: false },
    ],
    total_seconds: 32400, total_target_seconds: 43200, total_done: false,
  },
  ...extra,
});

test('a challenge shows its players and the total, escaped, with a link to the game', async () => {
  installApi({ 'GET /challenges': [challenge()] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.equal(document.querySelectorAll('.ch-card').length, 1);
  assert.equal(document.querySelector('.ch-title a').getAttribute('href'), '#/game/hades');
  assert.equal(document.querySelectorAll('.ch-title b').length, 0);
  assert.deepEqual(text('.ch-players .ch-name'), ['Ana (tú)', 'Bea']);
  assert.equal(document.querySelectorAll('.ch-players .ch-bar.ok').length, 1); // only Ana reached her part
  assert.match(text('.ch-total')[0], /9 h \/ 12 h/);
  assert.match(main().textContent, /mínimo 5 h cada uno y 12 h entre todos/);
  assert.equal(document.querySelector('#chLaunch'), null); // only an admin launches
  assert.equal(document.querySelector('[data-delete]'), null);
});

test('the challenges are grouped by where they are in time', async () => {
  installApi({ 'GET /challenges': [challenge({ id: 1 }), challenge({ id: 2, status: 'upcoming', title: 'Próximo' }), challenge({ id: 3, status: 'finished', title: 'Pasado' })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.deepEqual(text('.section-title'), ['En marcha', 'Próximos', 'Terminados']);
});

test('leaving and coming back asks the API about the caller only', async () => {
  const calls = installApi({ 'GET /challenges': [challenge()], 'PUT /challenges/5/participation': challenge({ taking_part: false }) });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('[data-part="leave"]').click();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'PUT').map((c) => c.path), ['/challenges/5/participation?joined=false']);
});

test('a challenge you left says so and offers to join again', async () => {
  installApi({ 'GET /challenges': [challenge({ taking_part: false })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /No participas en este reto/);
  assert.equal(document.querySelector('[data-part]').dataset.part, 'join');
  assert.equal(document.querySelector('.ch-players'), null);
});

test('an admin can launch and delete; deleting needs a second press', async () => {
  const calls = installApi({ 'GET /challenges': [challenge()], 'DELETE /challenges/5': { message: 'ok' } });
  await page.render({ main: main(), user: ROOT });
  await settle();
  assert.ok(document.querySelector('#chLaunch'));
  const button = document.querySelector('[data-delete]');
  button.click();
  assert.equal(calls.filter((c) => c.method === 'DELETE').length, 0);
  assert.match(button.textContent, /¿Seguro\?/);
  button.click();
  await settle();
  assert.equal(calls.filter((c) => c.method === 'DELETE').length, 1);
});

test('without challenges the page says who can start one', async () => {
  installApi({ 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /Cuando un administrador lance uno/);
  installApi({ 'GET /challenges': [] });
  await page.render({ main: main(), user: ROOT });
  await settle();
  assert.match(main().textContent, /Lanza el primero/);
});

test('an error loading is shown', async () => {
  installApi({ 'GET /challenges': json({ detail: 'boom' }, 500) });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /Error cargando los retos/);
});

test('the history of a player lists the finished challenges with how they did', async () => {
  document.body.innerHTML = '<div id="h"></div>';
  installApi({ 'GET /challenges/player/1': [{ id: 5, title: 'Juego del mes: Hades', ends_on: '2026-09-30', done: true, group_done: false }, { id: 6, title: 'Otro', ends_on: '2026-08-31', done: false, group_done: false }] });
  await history.showChallengesHistory(document.getElementById('h'), 1, true);
  assert.deepEqual(text('.ch-history-item strong'), ['Juego del mes: Hades', 'Otro']);
  assert.deepEqual(text('.ch-history-item .pf-tag'), ['Cumpliste tu parte', 'No se cumplió']);
});

test('the empty history is worded for whose it is', async () => {
  document.body.innerHTML = '<div id="h"></div>';
  installApi({ 'GET /challenges/player/1': [] });
  await history.showChallengesHistory(document.getElementById('h'), 1, true);
  assert.match(document.getElementById('h').textContent, /Todavía no has terminado ningún reto/);
  installApi({ 'GET /challenges/player/2': [] });
  await history.showChallengesHistory(document.getElementById('h'), 2, false);
  assert.match(document.getElementById('h').textContent, /Todavía no ha terminado ningún reto/);
});
