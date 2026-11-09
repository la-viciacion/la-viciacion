import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';
import { current } from '../js/lib/seasons.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/season/index.js');
const main = () => document.getElementById('main');

const ANSWER = [
  { type: 'user_hours', data: [{ user_id: 1, name: 'Ana <b>', played_time: 7200 }, { user_id: 2, name: 'Bea', played_time: 3600 }, { user_id: 3, name: 'Cai', played_time: 0 }] },
  { type: 'games_most_played', data: [{ game_id: 'hades', name: 'Hades', played_time: 5400 }] },
  { type: 'user_days', data: [] },
];

test('it shows the running season and a card per ranking, with names as text', async () => {
  const calls = installApi({ 'GET /statistics/rankings?': ANSWER, 'GET /users/photo/': json({ detail: 'no' }, 404) });
  await page.render({ main: main() });
  await settle();
  assert.equal(text('h1')[0], `Temporada ${current()}`);
  assert.equal(calls[0].path.startsWith('/statistics/rankings?only_active=true&ranking=user_hours'), true);
  assert.equal(document.querySelectorAll('.ss-card').length, 11);
  assert.deepEqual(text('#ss-hours .ss-name'), ['Ana <b>', 'Bea']);
  assert.equal(document.querySelectorAll('.ss-name b').length, 0);
  assert.equal(document.querySelector('#ss-hours .ss-fill').style.width, '100%');
  assert.equal(document.querySelectorAll('#ss-hours .ss-fill')[1].style.width, '50%');
  assert.equal(document.querySelector('#ss-most-played a').getAttribute('href'), '#/game/hades');
  assert.match(text('#ss-days')[0], /Todavía no hay datos/);
});

test('it says so when the rankings cannot be loaded', async () => {
  installApi({ 'GET /statistics/rankings?': json({ detail: 'no' }, 500) });
  await page.render({ main: main() });
  await settle();
  assert.match(text('.pf-empty')[0], /No se han podido cargar/);
});
