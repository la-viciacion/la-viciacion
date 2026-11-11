import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, text } from './dom.js';

const window = installDom('<button id="open" data-search>Buscar</button>');
installStorage();
globalThis.location = window.location;
const calls = installApi({
  'GET /group/players': [{ user_id: 1, name: 'Marta', is_me: false, playing: null }, { user_id: 2, name: 'Álvaro', is_me: false, playing: { game_name: 'Hades' } }],
  'GET /games/catalog?limit=8&sort=played&q=hades': { items: [{ id: 'hades', name: 'Hades', image_url: null, have: true }, { id: 'hades-ii', name: 'Hades II', image_url: null, have: false }] },
  'GET /games/catalog': { items: [] },
});
const { closeSearch, mountSearch } = await import('../js/ui/search.js');

mountSearch(document, { is_admin: false });
afterEach(() => closeSearch());

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const type = async (value) => {
  const input = document.getElementById('searchInput');
  input.value = value;
  input.dispatchEvent(new window.Event('input', { bubbles: true }));
  await wait(320); // the delay before asking, and the answers
};
const open = () => document.getElementById('open').click();
const key = (name, extra = {}) => document.dispatchEvent(new window.KeyboardEvent('keydown', { key: name, bubbles: true, ...extra }));

test('it opens with the pages to go to and nothing is asked yet', () => {
  open();
  assert.ok(document.querySelector('.search-panel'));
  assert.equal(document.activeElement, document.getElementById('searchInput'));
  assert.deepEqual(text('.search-group'), ['Ir a']);
  assert.ok(text('.search-item .search-name').includes('Temporada'));
  assert.equal(calls.length, 0);
});

test('typing shows the pages, the players and the games that match', async () => {
  open();
  await type('hades');
  assert.deepEqual(text('.search-group'), ['Juegos']); // no page nor player is called that
  assert.deepEqual(text('.search-item .search-name'), ['Hades', 'Hades II']);
  assert.deepEqual(text('.search-item .pf-tag'), ['En tu biblioteca']);
  assert.equal(document.querySelector('.search-item').getAttribute('href'), '#/game/hades');
  await type('ma');
  assert.deepEqual(text('.search-group'), ['Jugadores']);
  assert.equal(document.querySelector('.search-item').getAttribute('href'), '#/player/1');
});

test('accents do not matter and a query that matches nothing says so', async () => {
  open();
  await type('alvaro');
  assert.deepEqual(text('.search-item .search-name'), ['Álvaro']);
  assert.deepEqual(text('.search-item .pf-tag'), ['Jugando']);
  await type('zzzz');
  assert.deepEqual(text('.search-empty'), ['No hay nada que coincida.']);
});

test('Enter goes to the first result and closes the panel', async () => {
  open();
  await type('hades');
  const link = document.querySelector('a.search-item');
  let clicked = false;
  link.addEventListener('click', (e) => { clicked = true; e.preventDefault(); });
  document.getElementById('searchInput').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  assert.ok(clicked);
  assert.equal(document.querySelector('.search-panel'), null);
});

test('Escape, the close button and a press outside close it; "/" and Ctrl+K open it', () => {
  for (const close of [
    () => key('Escape'),
    () => document.querySelector('[data-close]').click(),
    () => document.querySelector('.search-overlay').dispatchEvent(new window.MouseEvent('click', { bubbles: true })),
  ]) {
    open();
    close();
    assert.equal(document.querySelector('.search-panel'), null);
  }
  key('/');
  assert.ok(document.querySelector('.search-panel'));
  closeSearch();
  key('k', { ctrlKey: true });
  assert.ok(document.querySelector('.search-panel'));
});

test('"/" typed in a field does not open it', () => {
  const field = document.createElement('input');
  document.body.appendChild(field);
  field.focus();
  key('/');
  assert.equal(document.querySelector('.search-panel'), null);
  field.remove();
});
