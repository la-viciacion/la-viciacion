import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
globalThis.location = window.location;
const page = await import('../js/pages/recommendations/index.js');

const PICK = (id, name) => ({ game_id: id, game_name: name, image_url: null, genres: ['Indie'], players: [{ user_id: 2, username: 'bea', name: 'Bea' }], completed_by: 0, played_seconds: 0 });

test('it lists what the API recommends to the user and offers other ones', async () => {
  const calls = installApi({
    'GET /users/ana/recommendations': [PICK('celeste', 'Celeste <b>')],
    'GET /users/photo/': json({ detail: 'no' }, 404),
  });
  await page.render({ main: document.getElementById('main'), user: { id: 1, username: 'ana' } });
  await settle();
  assert.equal(calls[0].path, '/users/ana/recommendations');
  assert.equal(document.querySelector('h1').textContent, 'Recomendados');
  assert.deepEqual(text('.pf-game-title strong'), ['Celeste <b>']);
  assert.equal(document.querySelectorAll('.pf-game-title b').length, 0);
  assert.ok(document.querySelector('[data-more]'));
});

test('when there is nothing to recommend it says so', async () => {
  installApi({ 'GET /users/ana/recommendations': [] });
  await page.render({ main: document.getElementById('main'), user: { id: 1, username: 'ana' } });
  await settle();
  assert.match(text('.pf-empty')[0], /No hay nada que recomendarte/);
  assert.equal(document.querySelector('[data-more]'), null);
});
