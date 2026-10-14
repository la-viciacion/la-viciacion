import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
window.location.hash = '#/admin/games';
globalThis.location = window.location;
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
const admin = await import('../js/pages/admin/index.js');

const game = (name) => ({ id: name, name, dev: '', release_date: null, genres: '', image_url: null, played_seconds: 0, players: 0, sessions: 0 });

test('the search box keeps its focus and its text while the results of what was typed arrive', async () => {
  const searches = [];
  installApi({
    'GET /utils/platforms': [],
    'GET /manage/users': { items: [] },
    'GET /manage/achievements': [],
    'GET /manage/games': ({ path }) => {
      const search = new URLSearchParams(path.split('?')[1]).get('search') || '';
      searches.push(search);
      return { total: 1, items: [game(search ? `Resultado ${search}` : 'Todos')] };
    },
  });
  const main = document.getElementById('main');
  await admin.render({ main, user: { id: 1 } });
  await settle();

  const box = document.getElementById('admSearch');
  box.focus();
  box.value = 'poe';
  box.dispatchEvent(new window.Event('input', { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 400));
  await settle();

  assert.deepEqual(searches, ['', 'poe']);
  assert.match(main.textContent, /Resultado poe/);
  assert.equal(document.getElementById('admSearch'), box, 'the same input element, not a copy');
  assert.equal(document.activeElement, box);
  assert.equal(box.value, 'poe');
  admin.dispose();
});
