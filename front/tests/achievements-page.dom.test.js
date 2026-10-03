import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/achievements/index.js');

const LIST = [
  { id: 1, key: 'first', title: 'Primero <b>', description: 'Alguien lo hizo.', has_image: true, unlocked_by: 2, unlocked_by_me: true,
    players: [{ user_id: 1, name: 'Ana', times: 2, last: '2026-02-01' }, { user_id: 2, name: 'Bea', times: 1, last: '2025-01-01' }] },
  { id: 2, key: 'second', title: 'Segundo', description: 'Otro.', has_image: false, unlocked_by: 0, unlocked_by_me: false, players: [] },
];

const main = () => document.getElementById('main');
let calls;

beforeEach(async () => {
  calls = installApi({ 'GET /group/achievements': LIST });
  await page.render({ main: main() });
  await settle();
});

test('every achievement is a card, with names as text, and the count of yours', () => {
  assert.equal(calls[0].path, '/group/achievements');
  assert.deepEqual(text('.ach-title strong'), ['Primero <b>', 'Segundo']);
  assert.equal(document.querySelectorAll('.ach-title b').length, 0);
  assert.equal(text('.ach-count')[0], 'Tienes 1 de 2');
  assert.equal(document.querySelectorAll('.ach-card.mine').length, 1);
  assert.match(text('.ach-card')[0], /Lo tienes/);
});

test('it says who has it (with the repeats) and that nobody has the other', () => {
  assert.match(text('.ach-card')[0], /Lo han conseguido 2: Ana \(×2\) y Bea/);
  assert.match(text('.ach-card')[1], /Nadie lo ha conseguido todavía/);
});

test('the picture comes from the achievement image route only when there is one', () => {
  assert.equal(document.querySelector('.ach-card img').getAttribute('src'), '/api/v1/utils/achievement-image/first');
  assert.equal(document.querySelectorAll('.ach-card img').length, 1);
  assert.equal(document.querySelectorAll('.ach-img-placeholder').length, 1);
});

test('an error says so', async () => {
  installApi({ 'GET /group/achievements': json({ detail: 'boom' }, 500) });
  await page.render({ main: main() });
  await settle();
  assert.match(main().textContent, /Error cargando los logros: boom/);
});
