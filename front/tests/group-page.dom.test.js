import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/group/index.js');

const today = new Date().toLocaleDateString('sv-SE');
const ITEMS = [
  { type: 'completed', day: today, user_id: 2, name: 'Bea', game_id: 'hades', game_name: 'Hades <b>', score: 92 },
  { type: 'played', day: today, user_id: 1, name: 'Ana', game_id: 'celeste', game_name: 'Celeste', seconds: 5400 },
  { type: 'achievement', day: '2026-01-02', user_id: 3, name: 'Cai', game_id: null, game_name: null, title: 'Madrugador' },
];

let calls;
const main = () => document.getElementById('main');

beforeEach(async () => {
  calls = installApi({
    'GET /activity?limit=30&offset=0': { items: ITEMS, has_more: true },
    'GET /activity?limit=30&offset=3': { items: [{ type: 'started', day: '2026-01-01', user_id: 1, name: 'Ana', game_id: 'celeste', game_name: 'Celeste' }], has_more: false },
    'GET /users/photo/': json({ detail: 'no' }, 404),
  });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
});

test('it shows each event as a sentence under its day, with names as text and links to the game page', () => {
  assert.equal(calls[0].path, '/activity?limit=30&offset=0');
  assert.equal(text('.ac-day')[0], 'Hoy');
  assert.match(text('.ac-day')[1], /2026/);
  assert.match(text('.ac-text')[0], /Bea completó Hades <b> 92/);
  assert.equal(document.querySelectorAll('.ac-text b').length, 0);
  assert.match(text('.ac-text')[1], /Ana jugó 1 h 30 min a Celeste/);
  assert.match(text('.ac-text')[2], /Cai desbloqueó el logro «Madrugador»$/);
  assert.equal(document.querySelector('.ac-text a').getAttribute('href'), '#/game/hades');
});

test('"Mostrar más" asks for the next page from where it stopped and goes away at the end', async () => {
  document.querySelector('#acMore').click();
  await settle();
  assert.equal(calls.at(-1).path, '/activity?limit=30&offset=3');
  assert.equal(document.querySelectorAll('.ac-event').length, 4);
  assert.equal(document.querySelector('#acMore'), null);
});
