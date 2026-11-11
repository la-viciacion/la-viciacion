import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';
import { current } from '../js/lib/seasons.js';

installStorage();
const window = installDom('<main id="main"></main>', 'http://localhost/');
globalThis.location = window.location;
globalThis.history = window.history;
const page = await import('../js/pages/season/index.js');
const main = () => document.getElementById('main');
const freshMain = () => { main().replaceWith(main().cloneNode(false)); return main(); }; // a page listens on its own <main>, as the router gives it

const ANSWER = [
  { type: 'user_hours', data: [{ user_id: 1, name: 'Ana <b>', played_time: 7200 }, { user_id: 2, name: 'Bea', played_time: 3600 }, { user_id: 3, name: 'Cai', played_time: 0 }, { user_id: 4, name: 'Dan', played_time: 0 }] },
  { type: 'user_days', data: [{ user_id: 1, name: 'Ana', played_days: 8 }, { user_id: 2, name: 'Bea', played_days: 2 }] },
  { type: 'user_played_games', data: [{ user_id: 2, name: 'Bea', played_games: 5 }] },
  { type: 'user_ratio', data: [{ user_id: 1, name: 'Ana', ratio: 0.5 }] },
  { type: 'games_most_played', data: [{ game_id: 'hades', name: 'Hades', image_url: 'https://img/hades.jpg', played_time: 5400 }, { game_id: 'x', name: 'Sin portada', image_url: null, played_time: 600 }, { game_id: 'a', name: 'A', image_url: 'https://img/a.jpg', played_time: 500 }, { game_id: 'b', name: 'B', image_url: 'https://img/b.jpg', played_time: 400 }] },
  { type: 'achievements', data: [] },
];

test('it shows the running season and a card per ranking, with names as text', async () => {
  const calls = installApi({ 'GET /statistics/rankings?': ANSWER, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: main() });
  await settle();
  assert.equal(text('h1')[0], `Temporada ${current()}`);
  assert.equal(calls[0].path.startsWith(`/statistics/rankings?only_active=true&season=${current()}&ranking=user_hours`), true);
  assert.equal(document.querySelectorAll('.ss-card').length, 9);
  assert.deepEqual(text('#ss-hours .ss-name'), ['Bea', 'Ana <b>', 'Cai', 'Dan']); // the podium puts the second at the left of the first; a player with nothing is still there
  assert.equal(document.querySelectorAll('.ss-name b').length, 0);
  assert.match(text('#ss-achievements')[0], /Todavía no hay datos/);
});

test('every ranking is a podium, the second at the left of the first', async () => {
  installApi({ 'GET /statistics/rankings?': ANSWER, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: main() });
  await settle();
  assert.deepEqual(text('#ss-days .ss-name'), ['Bea', 'Ana']);
  assert.deepEqual(text('#ss-days .ss-value'), ['2 días', '8 días']);
  assert.equal(document.querySelectorAll('#ss-games .ss-step').length, 1);
  assert.equal(text('#ss-ratio .ss-value')[0], '50 %');
});

test('the most played games show their cover, or a placeholder, and link to the game', async () => {
  installApi({ 'GET /statistics/rankings?': ANSWER, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: main() });
  await settle();
  const covers = document.querySelectorAll('#ss-most-played .ss-cover');
  assert.equal(covers[1].getAttribute('src'), 'https://img/hades.jpg');
  assert.equal(covers[0].tagName, 'DIV');
  assert.equal(document.querySelectorAll('#ss-most-played .ss-cover').length, 4);
  assert.equal(document.querySelectorAll('#ss-most-played .ss-row .ss-cover').length, 1); // beyond the podium the cover is there too
  assert.equal(document.querySelectorAll('#ss-most-played a')[1].getAttribute('href'), '#/game/hades');
});

test('it says so when the rankings cannot be loaded', async () => {
  installApi({ 'GET /statistics/rankings?': json({ detail: 'no' }, 500) });
  await page.render({ main: main() });
  await settle();
  assert.match(text('.pf-empty')[0], /No se han podido cargar/);
});

test('there is a pill per season, the running one pressed, and the address picks another', async () => {
  const calls = installApi({ 'GET /statistics/rankings?': ANSWER, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  window.location.hash = '#/season/' + (current() - 1);
  await page.render({ main: freshMain() });
  await settle();
  assert.equal(text('h1')[0], `Temporada ${current() - 1}`);
  assert.match(calls[0].path, new RegExp(`season=${current() - 1}&`));
  assert.equal(document.querySelectorAll('#main [data-season]').length, current() - 2023 + 2); // a pill per season and the hall of fame
  assert.equal(document.querySelector('[data-season][aria-pressed="true"]').textContent, String(current() - 1));
  assert.equal(document.querySelectorAll('.ss-card').length, 8); // no current streak in an old season
  assert.deepEqual(text('#ss-hours .ss-name'), ['Bea', 'Ana <b>']); // Cai and Dan did nothing that season: they are not listed, however they are today
  assert.match(calls[0].path, /only_active=false/);
  window.location.hash = '';
});

test('pressing a season loads it, follows it in the address and the last answer wins', async () => {
  const calls = installApi({ 'GET /statistics/rankings?': ANSWER, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: freshMain() });
  await settle();
  document.querySelector(`[data-season="${current() - 1}"]`).click();
  assert.equal(window.location.hash, `#/season/${current() - 1}`);
  document.querySelector(`[data-season="${current()}"]`).click(); // pressed before the older one answered
  assert.equal(window.location.hash, '#/season');
  await settle();
  assert.equal(text('h1')[0], `Temporada ${current()}`);
  assert.equal(document.querySelectorAll('.ss-card').length, 9);
  assert.equal(calls.filter((c) => c.path.startsWith('/statistics/rankings')).length, 3);
});

const FAME = {
  seasons: [
    { season: 2025, champions: { hours: [{ user_id: 2, name: 'Bea', value: 7200 }, { user_id: 3, name: 'Cai <i>', value: 7200 }], days: [{ user_id: 2, name: 'Bea', value: 1 }], games: [], completed: [], achievements: [], streak: [] } },
    { season: 2024, champions: { hours: [], days: [], games: [], completed: [], achievements: [], streak: [] } },
  ],
  titles: [{ user_id: 2, name: 'Bea', titles: 2 }, { user_id: 3, name: 'Cai <i>', titles: 1 }],
};

test('the hall of fame shows who has most titles and the champions of each season, a tie giving a title to each', async () => {
  const calls = installApi({ 'GET /statistics/hall-of-fame': FAME, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  window.location.hash = '#/season/fame';
  await page.render({ main: freshMain() });
  await settle();
  assert.equal(calls[0].path, '/statistics/hall-of-fame');
  assert.equal(text('h1')[0], 'Salón de la fama');
  assert.equal(document.querySelector('[data-season="fame"]').getAttribute('aria-pressed'), 'true');
  assert.deepEqual(text('[aria-label="Más títulos"] .ss-value'), ['1 título', '2 títulos']); // on the podium the second stands at the left of the first
  assert.equal(document.querySelectorAll('.hf-card').length, 2); // the titles and the one season with champions
  assert.deepEqual(text('[aria-label="Temporada 2025"] .hf-tile:first-child .ss-name'), ['Bea', 'Cai <i>']);
  assert.deepEqual(text('[aria-label="Temporada 2025"] .hf-tile:first-child .hf-figure'), ['2 h']); // a tie shares one figure
  assert.equal(document.querySelectorAll('[aria-label="Temporada 2025"] .hf-tile').length, 6);
  assert.equal(document.querySelectorAll('.hf-card i').length, 0); // names are text
  window.location.hash = '';
});

test('the hall of fame can be reached from the pills and says so when no season is over', async () => {
  installApi({ 'GET /statistics/rankings?': ANSWER, 'GET /statistics/hall-of-fame': { seasons: [], titles: [] }, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: freshMain() });
  await settle();
  document.querySelector('[data-season="fame"]').click();
  assert.equal(window.location.hash, '#/season/fame');
  await settle();
  assert.match(text('.pf-empty')[0], /ninguna temporada/);
  window.location.hash = '';
});
