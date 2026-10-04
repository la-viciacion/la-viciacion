import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
globalThis.location = window.location;
const page = await import('../js/pages/wishlist/index.js');

const GAME = (id, name, extra = {}) => ({
  id, name, image_url: null, genres: ['Indie', 'Platformer', 'Extra'], release_date: null, days_until: null,
  added_at: '2026-10-01T10:00:00', wanted_by: [], ...extra,
});

const LISTS = {
  upcoming: [
    GAME('soon', 'Soon <b>', { release_date: '2026-10-14', days_until: 10, wanted_by: [{ user_id: 2, username: 'bea', name: 'Bea' }] }),
    GAME('tba', 'Tba'),
  ],
  wanted: [GAME('out', 'Out', { release_date: '2020-01-01' })],
};

let calls;
let lists;
const main = () => document.getElementById('main');

beforeEach(async () => {
  lists = LISTS;
  calls = installApi({
    'GET /group/wishlist': () => lists,
    'DELETE /users/ana/wishlist/soon': () => { lists = { ...LISTS, upcoming: LISTS.upcoming.slice(1) }; return { game_id: 'soon', wished: false }; },
  });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
});

test('the upcoming releases come first, with the countdown, and names are text', () => {
  assert.equal(text('h1')[0], 'Lista de deseados');
  assert.deepEqual(text('.section-title'), ['Próximos lanzamientos', 'Quiero jugar']);
  assert.deepEqual(text('.gc-name'), ['Soon <b>', 'Tba', 'Out']);
  assert.equal(document.querySelectorAll('.gc-name b').length, 0);
  assert.match(text('.gc-meta')[0], /^En 10 días · /);
  assert.equal(text('.gc-meta')[1], 'Sin fecha confirmada');
  assert.equal(document.querySelector('.wl-link').getAttribute('href'), '#/game/soon');
});

test('it names who else wants a game', () => {
  assert.deepEqual(text('.gc-body .pf-sub'), ['Lo quiere Bea']);
});

test('removing a game asks the API and redraws the list', async () => {
  document.querySelector('[data-remove="soon"]').click();
  await settle();
  assert.deepEqual(calls.filter((c) => c.method === 'DELETE').map((c) => c.path), ['/users/ana/wishlist/soon']);
  assert.deepEqual(text('.gc-name'), ['Tba', 'Out']);
});

test('an empty list invites to add games, and an empty half says so', async () => {
  lists = { upcoming: [], wanted: [] };
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
  assert.match(main().textContent, /Tu lista está vacía/);

  lists = { upcoming: [], wanted: [GAME('out', 'Out')] };
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
  assert.match(main().textContent, /Ningún juego pendiente de salir/);
});
