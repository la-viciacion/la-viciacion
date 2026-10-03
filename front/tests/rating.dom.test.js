import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
installDom();
const { openRating } = await import('../js/pages/home/rating.js');
const { closeAllModals } = await import('../js/ui/modal.js');

afterEach(() => closeAllModals());

const open = (extra = {}) => openRating({ username: 'ana', game: { id: 'celeste', name: 'Celeste <b>' }, ...extra });
const field = () => document.querySelector('input[name="score"]');
const submit = async (value) => {
  field().value = value;
  document.querySelector('#rateForm').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
};

test('it asks for the rating of the game, shown as text, with the one it already has', () => {
  open({ current: 80 });
  assert.equal(document.querySelector('.modal-header h3').textContent, '¿Quieres puntuarlo?');
  assert.equal(document.querySelector('#rateBody strong').textContent, 'Celeste <b>');
  assert.equal(document.querySelectorAll('#rateBody b').length, 0);
  assert.equal(field().value, '80');
});

test('saving rates the game, closes the question and tells the caller', async () => {
  const calls = installApi({ 'PUT /users/ana/games/celeste/score': { game_id: 'celeste', score: 92 } });
  let saved = 0;
  open({ onSaved: () => saved++ });
  await submit('92');
  assert.deepEqual(calls.map((c) => [c.method, c.path, c.body]), [['PUT', '/users/ana/games/celeste/score', { score: 92 }]]);
  assert.equal(document.querySelectorAll('.modal-overlay').length, 0);
  assert.equal(saved, 1);
});

test('a value that is not 1-100 is refused without asking the API', async () => {
  const calls = installApi({});
  open();
  for (const value of ['', '0', '101', '7.5']) {
    await submit(value);
    assert.match(document.querySelector('.sess-error').textContent, /entero de 1 a 100/, value);
  }
  assert.equal(calls.length, 0);
  assert.equal(document.querySelectorAll('.modal-overlay').length, 1);
});

test('"Ahora no" closes it and rates nothing', async () => {
  const calls = installApi({});
  open();
  document.querySelector('.sess-actions [data-close]').click();
  assert.equal(document.querySelectorAll('.modal-overlay').length, 0);
  assert.equal(calls.length, 0);
});

test('an API error stays in the question so the player can try again', async () => {
  installApi({ 'PUT /users/ana/games/celeste/score': json({ detail: 'Este juego no está en tu biblioteca' }, 404) });
  open();
  await submit('50');
  assert.match(document.querySelector('.sess-error').textContent, /no está en tu biblioteca/);
  assert.equal(document.querySelectorAll('.modal-overlay').length, 1);
});
