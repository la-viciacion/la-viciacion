import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { closeAllModals } = await import('../js/ui/modal.js');
const page = await import('../js/pages/challenges/index.js');
const history = await import('../js/ui/challenges-history.js');

afterEach(() => closeAllModals());

const main = () => document.getElementById('main');
const ANA = { id: 1, username: 'ana', is_admin: false };
const ROOT = { id: 9, username: 'root', is_admin: true };
const DEBT = { seconds: 40 * 3600, games: 4, open_games: 5 };

const challenge = (extra = {}) => ({
  id: 5, kind: 'game_of_month', label: 'Juego del mes', scope: 'group', title: 'Juego del mes: Hades <b>', status: 'active',
  starts_on: '2026-10-01', ends_on: '2026-10-31', params: { min_hours_each: 5, min_hours_total: 12 },
  game: { id: 'hades', name: 'Hades', image_url: null }, owner: null, taking_part: true, can_opt_out: true,
  progress: {
    players: [
      { user_id: 1, name: 'Ana', seconds: 25200, target_seconds: 18000, done: true },
      { user_id: 2, name: 'Bea', seconds: 7200, target_seconds: 18000, done: false },
    ],
    total_seconds: 32400, total_target_seconds: 43200, total_done: false,
  },
  ...extra,
});

const personal = (extra = {}) => ({
  id: 7, kind: 'new_genre', label: 'Probar un género', scope: 'user', title: 'Probar un género: Metroidvania', status: 'active',
  starts_on: '2026-10-01', ends_on: '2026-10-30', params: { genre: 'Metroidvania', mode: 'play', duration: 'month', hours: 2 },
  game: null, owner: { id: 1, name: 'Ana' }, taking_part: true, can_opt_out: false,
  progress: { players: [{ user_id: 1, name: 'Ana', seconds: 3600, target_seconds: 7200, done: false }] },
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
  assert.equal(document.querySelector('[data-delete]'), null); // a group challenge is deleted from the admin panel
});

test('the challenges are in blocks: the group\'s, the viewer\'s own and the other players\'', async () => {
  const bea = personal({ id: 8, owner: { id: 2, name: 'Bea' }, title: 'Probar un género: RPG' });
  installApi({ 'GET /challenges': [challenge(), personal(), bea] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.deepEqual(text('.section-title'), ['Del grupo', 'Tuyos', 'De otros jugadores']);
  assert.deepEqual(text('.ch-title').map((t) => t.split('\n')[0].trim().slice(0, 12)), ['Juego del me', 'Probar un gé', 'Probar un gé']);
  assert.match(text('.ch-card')[2], /Bea · /); // the owner of somebody else's
});

test('a personal challenge shows its single bar and only its owner can delete it, with a second press', async () => {
  const calls = installApi({ 'GET /challenges': [personal(), personal({ id: 8, owner: { id: 2, name: 'Bea' } })], 'DELETE /challenges/7': { message: 'ok' } });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.equal(document.querySelectorAll('[data-delete]').length, 1);
  assert.match(main().textContent, /jugar 2 h a un juego de Metroidvania que no tuvieras antes/);
  assert.equal(document.querySelector('.ch-total'), null);
  assert.equal(document.querySelector('[data-part]'), null); // nobody leaves a personal one
  const button = document.querySelector('[data-delete]');
  button.click();
  assert.equal(calls.filter((c) => c.method === 'DELETE').length, 0);
  assert.match(button.textContent, /¿Seguro\?/);
  button.click();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'DELETE').map((c) => c.path), ['/challenges/7']);
});

test('a completion is counted in games', async () => {
  const done = personal({ params: { genre: 'RPG', mode: 'complete', duration: 'week' }, progress: { players: [{ user_id: 1, name: 'Ana', count: 1, target_count: 1, done: true }] } });
  installApi({ 'GET /challenges': [done] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(text('.ch-row')[0], /1 \/ 1 juego ✓/);
  assert.match(main().textContent, /completar un juego de RPG/);
  assert.equal(document.querySelectorAll('.ch-bar.ok').length, 1);
});

test('leaving and coming back asks the API about the caller only', async () => {
  const calls = installApi({ 'GET /challenges': [challenge()], 'PUT /challenges/5/participation': challenge({ taking_part: false }) });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('[data-part="leave"]').click();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'PUT').map((c) => c.path), ['/challenges/5/participation?joined=false']);
});

test('a group challenge you left says so and offers to join again', async () => {
  installApi({ 'GET /challenges': [challenge({ taking_part: false })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /No participas en este reto/);
  assert.equal(document.querySelector('[data-part]').dataset.part, 'join');
  assert.equal(document.querySelector('.ch-players'), null);
});

test('not even an admin launches or deletes a group challenge from this page: that is the admin panel', async () => {
  installApi({ 'GET /challenges': [challenge()] });
  await page.render({ main: main(), user: ROOT });
  await settle();
  assert.equal(document.querySelector('[data-delete]'), null);
  assert.ok(document.querySelector('[data-part]')); // but an admin takes part like anybody
});

test('the new challenge form asks for a genre, the goal and the duration, and sends them', async () => {
  const GENRES = [{ genre: 'Action', games: 3, played: true }, { genre: 'Metroidvania', games: 2, played: false }];
  const calls = installApi({ 'GET /challenges/debt': DEBT, 'GET /challenges/genres': GENRES, 'GET /challenges': [], 'POST /challenges': personal() });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  assert.deepEqual(text('select[name="genre"] option'), ['Action (3)', 'Metroidvania (2) · nuevo para ti']);
  const form = document.querySelector('.modal-content form');
  assert.equal(form.elements.hours.value, '2'); // the default
  assert.equal(form.elements.duration.value, 'month');
  form.elements.genre.value = 'Metroidvania';
  form.elements.mode.value = 'complete';
  form.elements.mode.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(document.querySelector('[data-for="play"]').hidden, true);
  form.requestSubmit();
  await settle();
  const post = calls.find((c) => c.method === 'POST');
  assert.deepEqual(post.body, { kind: 'new_genre', options: { genre: 'Metroidvania', mode: 'complete', duration: 'month' } });
});

test('playing sends the hours', async () => {
  const calls = installApi({ 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [{ genre: 'RPG', games: 1, played: false }], 'GET /challenges': [], 'POST /challenges': personal() });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  form.elements.hours.value = '3.5';
  form.elements.duration.value = 'week';
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body.options, { genre: 'RPG', mode: 'play', duration: 'week', hours: 3.5 });
});

test('an error from the API stays in the form', async () => {
  installApi({ 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [{ genre: 'RPG', games: 1, played: false }], 'GET /challenges': [], 'POST /challenges': json({ detail: 'Ya existe un reto igual' }, 409) });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  document.querySelector('.modal-content form').requestSubmit();
  await settle();
  assert.match(document.querySelector('.adm-error').textContent, /Ya existe un reto igual/);
});

test('without challenges each block says how to get one', async () => {
  installApi({ 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /No hay ningún reto del grupo/);
  assert.match(main().textContent, /No tienes ningún reto/);
});

test('an error loading is shown', async () => {
  installApi({ 'GET /challenges': json({ detail: 'boom' }, 500) });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(main().textContent, /Error cargando los retos/);
});

test('the history of a player lists the finished challenges with how they did', async () => {
  document.body.innerHTML = '<div id="h"></div>';
  installApi({ 'GET /challenges/player/1': [
    { id: 5, title: 'Juego del mes: Hades', scope: 'group', ends_on: '2026-09-30', done: true, group_done: false },
    { id: 6, title: 'Otro', scope: 'group', ends_on: '2026-08-31', done: false, group_done: false },
    { id: 7, title: 'Probar un género: RPG', scope: 'user', ends_on: '2026-08-01', done: true, group_done: null },
  ] });
  await history.showChallengesHistory(document.getElementById('h'), 1, true);
  assert.deepEqual(text('.ch-history-item strong'), ['Juego del mes: Hades', 'Otro', 'Probar un género: RPG']);
  assert.deepEqual(text('.ch-history-item .pf-tag'), ['Cumpliste tu parte', 'No se cumplió', 'Lo conseguiste']);
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

test('the kind of challenge decides which options show and the form starts on trying a genre', async () => {
  document.body.innerHTML = '<main id="main"></main>'; // the tests of the history above replaced it
  installApi({ 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [{ genre: 'RPG', games: 1, played: false }], 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  assert.equal(form.querySelector('[data-kind="new_genre"]').hidden, false);
  assert.equal(form.querySelector('[data-kind="debt_reduction"]').hidden, true);
  form.elements.kind.value = 'debt_reduction';
  form.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(form.querySelector('[data-kind="new_genre"]').hidden, true);
  assert.equal(form.querySelector('[data-kind="debt_reduction"]').hidden, false);
});

test('before accepting a percentage of the debt the form says how many hours it is', async () => {
  document.body.innerHTML = '<main id="main"></main>'; // the tests of the history above replaced it
  installApi({ 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [], 'GET /challenges': [] });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  form.elements.kind.value = 'debt_reduction';
  form.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.match(document.querySelector('#chDebtPreview').textContent, /El 25 % de tu deuda son unas 10 h \(tu deuda ahora: 40 h en 4 juegos\)/);
  form.elements.debtValue.value = '12.5';
  form.elements.debtValue.dispatchEvent(new window.Event('input', { bubbles: true }));
  assert.match(document.querySelector('#chDebtPreview').textContent, /El 12,5 % de tu deuda son unas 5 h/);
});

test('launching a debt challenge sends the percentage or the games', async () => {
  document.body.innerHTML = '<main id="main"></main>'; // the tests of the history above replaced it
  const calls = installApi({ 'GET /challenges/debt': DEBT, 'GET /challenges/genres': [], 'GET /challenges': [], 'POST /challenges': personal() });
  await page.render({ main: main(), user: ANA });
  await settle();
  document.querySelector('#chNew').click();
  await settle();
  const form = document.querySelector('.modal-content form');
  form.elements.kind.value = 'debt_reduction';
  form.elements.kind.dispatchEvent(new window.Event('change', { bubbles: true }));
  form.elements.debtValue.value = '30';
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body, { kind: 'debt_reduction', options: { mode: 'percent', duration: 'month', percent: 30 } });
  document.querySelector('#chNew').click();
  await settle();
  const second = document.querySelector('.modal-content form');
  second.elements.kind.value = 'debt_reduction';
  second.elements.debtMode.value = 'games';
  second.elements.debtMode.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(second.elements.debtValue.max, '5'); // as many as are open
  second.elements.debtValue.value = '2';
  second.requestSubmit();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'POST').at(-1).body.options, { mode: 'games', duration: 'month', games: 2 });
});

test('a debt challenge shows its share of the debt paid', async () => {
  document.body.innerHTML = '<main id="main"></main>'; // the tests of the history above replaced it
  const progress = { players: [{ user_id: 1, name: 'Ana', percent: 12.5, target_percent: 25, paid_seconds: 18000, initial_seconds: 144000, done: false }] };
  installApi({ 'GET /challenges': [personal({ kind: 'debt_reduction', label: 'Bajar la deuda', title: 'Bajar la deuda un 25 %', params: { mode: 'percent', percent: 25, duration: 'month' }, progress })] });
  await page.render({ main: main(), user: ANA });
  await settle();
  assert.match(text('.ch-row')[0], /12,5 % \/ 25 %/);
  assert.match(main().textContent, /saldar el 25 % de lo que te quedaba por jugar al empezar/);
});
