import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, settle, text } from './dom.js';

installStorage();
installDom('<span id="bellBadge">3</span><main id="main"></main>', 'http://localhost/');
const page = await import('../js/pages/notifications/index.js');

const ITEMS = [
  { id: 7, title: '🏆 Logro <b>', body: 'Ana ha ganado algo', url: '#/achievements', created_at: '2026-10-20T10:00:00', read: false },
  { id: 5, title: 'La Viciación', body: 'Ana empieza Hades', url: '/', created_at: '2026-10-19T09:00:00', read: true },
];

let calls;
let items;
const main = () => document.getElementById('main');

beforeEach(async () => {
  items = ITEMS;
  calls = installApi({
    'GET /notifications/': () => ({ unread: items.filter((n) => !n.read).length, items }),
    'POST /notifications/read': { unread: 0 },
    'DELETE /notifications/7': { deleted: 1 },
    'DELETE /notifications/': () => {
      items = [];
      return { deleted: 2 };
    },
  });
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
});

test('it lists the notices as text, links the ones that open a page and highlights the unread ones', () => {
  assert.deepEqual(text('.nt-title'), ['🏆 Logro <b>', 'La Viciación']);
  assert.equal(main().querySelectorAll('.nt-title b').length, 0);
  assert.equal(main().querySelector('a.nt-link').getAttribute('href'), '#/achievements');
  assert.equal(main().querySelectorAll('div.nt-link').length, 1);
  assert.deepEqual([...main().querySelectorAll('.nt-card')].map((c) => c.classList.contains('unread')), [true, false]);
});

test('the game links of a body are anchors: RAWG opens in a new tab, the app navigates, anything else is text', async () => {
  items = [
    { id: 9, title: 'La Viciación', url: '#/game/g1', created_at: '2026-10-20T10:00:00', read: true,
      body: `Ana empieza [Hades](https://rawg.io/games/hades), [Doom](http://localhost/#/game/doom) y [Mal](https://evil.test/x)`,
    },
  ];
  await page.render({ main: main(), user: { id: 1, username: 'ana' } });
  await settle();
  const [rawg, app] = main().querySelectorAll('.nt-body a.game-link');
  assert.equal(rawg.getAttribute('href'), 'https://rawg.io/games/hades');
  assert.equal(rawg.getAttribute('target'), '_blank');
  assert.equal(app.getAttribute('href'), '#/game/doom');
  assert.equal(app.getAttribute('target'), null);
  assert.match(main().querySelector('.nt-body').textContent, /y \[Mal\]\(https:\/\/evil\.test\/x\)$/);
  assert.equal(main().querySelectorAll('a.nt-link').length, 0);
  assert.equal(main().querySelector('div.nt-link').dataset.open, '#/game/g1');
});

test('seeing the unread ones marks them as read and clears the bell', () => {
  assert.ok(calls.some((c) => c.method === 'POST' && c.path === '/notifications/read'));
  assert.equal(document.getElementById('bellBadge').hidden, true);
});

test('a notice is deleted on its own', async () => {
  items = [ITEMS[1]];
  main().querySelector('[data-remove="7"]').click();
  await settle();
  assert.ok(calls.some((c) => c.method === 'DELETE' && c.path === '/notifications/7'));
  assert.deepEqual(text('.nt-title'), ['La Viciación']);
});

test('emptying the inbox asks for a second click', async () => {
  const button = main().querySelector('#ntClear');
  button.click();
  assert.equal(button.textContent, '¿Vaciar todo?');
  assert.ok(!calls.some((c) => c.method === 'DELETE'));
  button.click();
  await settle();
  assert.ok(calls.some((c) => c.method === 'DELETE' && c.path === '/notifications/'));
  assert.match(main().textContent, /No tienes avisos/);
  assert.equal(button.hidden, true);
  page.dispose();
});
