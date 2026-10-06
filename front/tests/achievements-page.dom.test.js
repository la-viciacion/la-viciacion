import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const page = await import('../js/pages/achievements/index.js');

const LIST = [
  { id: 1, key: 'first', title: 'Primero <b>', description: 'Alguien lo hizo.', has_image: true, unlocked_by: 2, unlocked_by_me: true,
    players: [{ user_id: 1, name: 'Ana', times: 2, last: '2026-02-01' }, { user_id: 2, name: 'Bea', times: 1, last: '2025-01-01' }] },
  { id: 2, hidden: true, unlocked_by_me: false },
];

const main = () => document.getElementById('main');
let calls;

beforeEach(async () => {
  calls = installApi({ 'GET /group/achievements': LIST });
  await page.render({ main: main() });
  await settle();
});

test('yours are cards, with names as text, and the rest are listed hidden with the count', () => {
  assert.equal(calls[0].path, '/group/achievements');
  assert.deepEqual(text('.ach-title strong'), ['Primero <b>', 'Logro oculto']);
  assert.equal(document.querySelectorAll('.ach-title b').length, 0);
  assert.equal(text('.ach-count')[0], 'Tienes 1 de 2');
  assert.equal(document.querySelectorAll('.ach-card').length, 2);
  assert.equal(document.querySelectorAll('.ach-card.mine').length, 1);
  assert.equal(document.querySelectorAll('.ach-card.hidden').length, 1);
  assert.doesNotMatch(text('.ach-card')[0], /Lo tienes/);
  assert.doesNotMatch(text('.ach-card')[1], /Segundo|Otro/);
});

test('it says who has the unlocked ones, with the repeats', () => {
  assert.match(text('.ach-card')[0], /Lo han conseguido 2: Ana \(×2\) y Bea/);
});

test('the picture comes from the achievement image route only when there is one', () => {
  assert.equal(document.querySelector('.ach-card img').getAttribute('src'), '/api/v1/utils/achievement-image/first');
  assert.equal(document.querySelectorAll('.ach-card img').length, 1);
  assert.equal(document.querySelectorAll('.ach-img-placeholder').length, 1);
});

test('what is not unlocked shows a lock, not a question mark', () => {
  assert.equal(text('.ach-card.hidden .ach-img-placeholder')[0], '🔒');
});

test('a special one shines in the colour of its level, an ordinary one does not, and the tag says which', async () => {
  installApi({ 'GET /group/achievements': [{ ...LIST[0], special: 1 }, { ...LIST[0], id: 3, title: 'Dorado', special: 2 }, { ...LIST[0], id: 4, title: 'Normal', special: 0 }, LIST[1]] });
  await page.render({ main: main() });
  await settle();
  const cards = document.querySelectorAll('.ach-card.mine');
  assert.ok(cards[0].classList.contains('special-1'));
  assert.ok(cards[1].classList.contains('special-2'));
  assert.ok(![...cards[2].classList].some((c) => c.startsWith('special-')));
  assert.match(text('.ach-card')[0], /Especial plateado/);
  assert.match(text('.ach-card')[1], /Especial dorado/);
  assert.doesNotMatch(text('.ach-card')[2], /Especial/);
});

test('a secret one says so, and being secret is not being special', async () => {
  installApi({ 'GET /group/achievements': [{ ...LIST[0], secret: true }, { ...LIST[0], id: 3, title: 'Normal' }, LIST[1]] });
  await page.render({ main: main() });
  await settle();
  assert.match(text('.ach-card')[0], /Secreto/);
  assert.doesNotMatch(text('.ach-card')[1], /Secreto/);
  assert.ok(![...document.querySelector('.ach-card').classList].some((c) => c.startsWith('special-')));  // no aura without a level
});

test('one the viewer has not unlocked, and is not secret, is shown in full but dimmed', async () => {
  installApi({ 'GET /group/achievements': [{ ...LIST[0], unlocked_by_me: false, unlocked_by: 0, players: [] }, LIST[1]] });
  await page.render({ main: main() });
  await settle();
  const [open] = document.querySelectorAll('.ach-card.locked');
  assert.match(open.textContent, /Primero <b>/);
  assert.match(open.textContent, /Alguien lo hizo/);
  assert.equal(document.querySelectorAll('.ach-card.mine').length, 0);
  assert.equal(text('.ach-count')[0], 'Tienes 0 de 2');
});

test('a secret one that is not unlocked still has the aura of its level, and says nothing else about itself', async () => {
  installApi({ 'GET /group/achievements': [LIST[1], { id: 5, hidden: true, unlocked_by_me: false, secret: true, special: 3 }] });
  await page.render({ main: main() });
  await settle();
  const [plain, special] = document.querySelectorAll('.ach-card.hidden');
  assert.ok(![...plain.classList].some((c) => c.startsWith('special-')));
  assert.ok(special.classList.contains('special-3'));
  assert.deepEqual(text('.ach-title strong'), ['Logro oculto', 'Logro oculto']);  // the aura is what tells them apart
  assert.doesNotMatch(special.textContent, /Secreto|Especial/);
});

test('one that has no season limit says it is unique, and the others do not', async () => {
  installApi({ 'GET /group/achievements': [{ ...LIST[0], lifetime: true }, { ...LIST[0], id: 3, title: 'Normal' }, LIST[1]] });
  await page.render({ main: main() });
  await settle();
  assert.match(text('.ach-card')[0], /Único/);
  assert.doesNotMatch(text('.ach-card')[1], /Único/);
  assert.doesNotMatch(text('.ach-card')[2], /Único/);  // what is hidden says nothing
});

test('an error says so', async () => {
  installApi({ 'GET /group/achievements': json({ detail: 'boom' }, 500) });
  await page.render({ main: main() });
  await settle();
  assert.match(main().textContent, /Error cargando los logros: boom/);
});
