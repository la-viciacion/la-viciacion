import assert from 'node:assert/strict';
import { afterEach, beforeEach, mock, test } from 'node:test';
import { installApi, installDom, installStorage, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
globalThis.location = window.location;
const page = await import('../js/pages/games/index.js');

const GAME = (id, name, extra = {}) => ({
  id, name, image_url: null, genres: ['Indie', 'Platformer', 'Extra'], release_date: null, players: 2, played_seconds: 7200,
  completed_by: 0, score_count: 2, score_mean: 80, have: false, my_score: null, my_completed: false, playing_now: false, last_activity: null, ...extra,
});

let calls;
const main = () => document.getElementById('main');

afterEach(() => mock.timers.reset());

beforeEach(async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  // the first key a request starts with wins: the longer ones go first
  calls = installApi({
    'GET /games/catalog?limit=24&offset=2&sort=activity': { total: 30, items: [GAME('zelda', 'Zelda')], genres: ['Indie', 'Platformer'] },
    'GET /games/catalog?limit=24&offset=0&sort=name': { total: 1, items: [GAME('hades', 'Hades')], genres: ['Indie', 'Platformer'] },
    'GET /games/catalog?limit=24&offset=0&sort=activity&q=hades': { total: 1, items: [GAME('hades', 'Hades')], genres: ['Indie'] },
    'GET /games/catalog?limit=24&offset=0&sort=activity&genre=Indie&library=have&playing=true': { total: 0, items: [], genres: [] },
    'GET /games/catalog?limit=24&offset=0&sort=activity': { total: 30, items: [GAME('celeste', 'Celeste <b>', { have: true, playing_now: true, wished: true }), GAME('hades', 'Hades', { players: 1, score_mean: null })], genres: ['Indie', 'Platformer'] },
  });
  await page.render({ main: main() });
  await settle();
});

test('the query string carries only what is set', () => {
  assert.equal(page.catalogQuery({ sort: 'activity', q: '', genre: '', library: '' }), 'limit=24&offset=0&sort=activity');
  assert.equal(page.catalogQuery({ sort: 'name', q: 'hades', genre: 'Indie', library: 'have', playing: true, rated: true }, 24),
    'limit=24&offset=24&sort=name&q=hades&genre=Indie&library=have&playing=true&rated=true');
});

test('it lists the games as cards linking to their page, with names as text and the count', () => {
  assert.equal(calls[0].path, '/games/catalog?limit=24&offset=0&sort=activity');
  assert.deepEqual(text('.gc-name'), ['Celeste <b>', 'Hades']);
  assert.equal(document.querySelectorAll('.gc-name b').length, 0);
  assert.equal(document.querySelector('.gc-card').getAttribute('href'), '#/game/celeste');
  assert.equal(text('#gcCount')[0], '30 juegos');
  assert.equal(document.querySelectorAll('.gc-card .score-badge').length, 1); // Hades has no ratings
  assert.deepEqual(text('.gc-card .pf-tag').slice(0, 5), ['Jugándose', 'En tu biblioteca', 'En tu lista', 'Indie', 'Platformer']); // two genres at most
});

test('the genres of the answer fill the genre filter', () => {
  assert.deepEqual([...document.querySelectorAll('#gcGenre option')].map((o) => o.value), ['', 'Indie', 'Platformer']);
});

test('"Mostrar más" asks from where it stopped', async () => {
  document.querySelector('#gcMore').click();
  await settle();
  assert.equal(calls.at(-1).path, '/games/catalog?limit=24&offset=2&sort=activity');
  assert.equal(document.querySelectorAll('.gc-card').length, 3);
});

test('the order, the toggles and the search reload the list from the start', async () => {
  const sort = document.querySelector('#gcSort');
  sort.value = 'name';
  sort.dispatchEvent(new window.Event('change'));
  await settle();
  assert.equal(calls.at(-1).path, '/games/catalog?limit=24&offset=0&sort=name');
  assert.deepEqual(text('.gc-name'), ['Hades']);

  sort.value = 'activity';
  sort.dispatchEvent(new window.Event('change'));
  await settle();
  const search = document.querySelector('#gcSearch');
  search.value = ' hades ';
  search.dispatchEvent(new window.Event('input'));
  const before = calls.length;
  mock.timers.tick(299);
  assert.equal(calls.length, before); // debounced
  mock.timers.tick(1);
  await settle();
  assert.equal(calls.at(-1).path, '/games/catalog?limit=24&offset=0&sort=activity&q=hades');
});

test('toggles and selects combine and an empty answer says so', async () => {
  const genre = document.querySelector('#gcGenre');
  genre.value = 'Indie';
  genre.dispatchEvent(new window.Event('change'));
  const library = document.querySelector('#gcLibrary');
  library.value = 'have';
  library.dispatchEvent(new window.Event('change'));
  document.querySelector('[data-toggle="playing"]').click();
  await settle();
  await settle(); // three reloads, the last one wins
  assert.equal(calls.at(-1).path, '/games/catalog?limit=24&offset=0&sort=activity&genre=Indie&library=have&playing=true');
  assert.equal(document.querySelector('[data-toggle="playing"]').getAttribute('aria-pressed'), 'true');
  assert.match(main().textContent, /Ningún juego coincide/);
});
