import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
window.location.hash = '#/admin/games';
globalThis.location = window.location;
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
const admin = await import('../js/pages/admin/index.js');

const game = (id, players, wishes) => ({ id, name: id, dev: '', release_date: null, genres: '', image_url: null, players, wishes, sessions: 0, unused: false, upcoming: false });

test('a count opens who it is made of, and a zero is plain text', async () => {
  const asked = [];
  installApi({
    'GET /utils/platforms': [{ id: 'pc', name: 'PC' }],
    'GET /manage/users': { items: [] },
    'GET /manage/achievements': [],
    'GET /manage/games/celeste/people': () => {
      asked.push('celeste');
      return {
        players: [{ user_id: 1, username: 'ana', name: 'Ana <b>', is_active: true, entries: [{ platform: 'pc', season: 2026 }] }],
        wishes: [{ user_id: 2, username: 'bea', name: 'Bea', is_active: false, added_at: '2026-10-01T10:00:00' }, { user_id: 1, username: 'ana', name: 'Ana <b>', is_active: true, added_at: '2026-10-02T10:00:00' }],
      };
    },
    'GET /manage/games': { total: 2, items: [game('celeste', 1, 2), game('hades', 0, 0)] },
  });
  const main = document.getElementById('main');
  await admin.render({ main, user: { id: 1 } });
  await settle();

  assert.equal(main.querySelectorAll('[data-act="game-people"]').length, 2, 'only the non-zero counts are buttons');
  main.querySelector('[data-act="game-people"][data-list="wishes"]').click();
  await settle();

  const modal = document.querySelector('.modal-content');
  assert.deepEqual([...modal.querySelectorAll('h4')].map((h) => h.textContent.replace(/\s+/g, ' ').trim()), ['Lo desean 2', 'Lo tienen en su biblioteca 1']);
  assert.match(modal.textContent, /PC 2026/);
  assert.match(modal.textContent, /\(inactivo\)/);
  assert.equal(modal.querySelector('b'), null, 'names are escaped');
  assert.equal(modal.querySelector('a').getAttribute('href'), '#/player/2');
  assert.deepEqual(asked, ['celeste']);
});
