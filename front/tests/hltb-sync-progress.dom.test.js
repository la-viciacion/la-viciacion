import assert from 'node:assert/strict';
import { afterEach, mock, test } from 'node:test';
import { closeAllModals } from '../js/ui/modal.js';
import { installApi, installDom, installStorage, settle, text } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { hltbSyncFlow } = await import('../js/pages/admin/hltb-sync.js');

afterEach(() => {
  closeAllModals();
  mock.timers.reset();
});

const amb = (name) => ({ game_id: name, name, candidates: [{ name: `${name} II`, year: 2020, hours: 12 }] });
const status = (extra) => ({
  state: 'running', total: 512, current: 'Game', updated: 0, unchanged: 0, ambiguous: [], not_found: [], no_time: [], errors: [], stop_reason: null, ...extra,
});

/** Opens the progress modal over a status that changes on every request: `next(n)` is the answer to the nth poll (the
 * flow asks once before opening the modal, which polls right away, so the first two get the same answer). */
async function open(next) {
  mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  installApi({ 'GET /manage/hltb-sync/status': () => next(Math.max(0, calls++ - 1)) });
  await hltbSyncFlow({ onDone: () => {} });
  await settle();
}

const tick = async () => {
  mock.timers.tick(2000);
  await settle();
};

test('the figures follow the run, tick after tick', async () => {
  await open((n) => status({ processed: 3 + n }));
  assert.match(text('.adm-progress-txt')[0], /^3 \/ 512 juegos · Game/);
  await tick();
  await tick();
  assert.match(text('.adm-progress-txt')[0], /^5 \/ 512 juegos · Game/);
  assert.match(document.querySelector('.adm-progress div').getAttribute('style'), /width:\s*1%/);
});

test('a list the admin is reading stays open and as it was, and the figures still move', async () => {
  await open((n) => status({ processed: 3 + n, ambiguous: Array.from({ length: Math.min(n + 1, 3) }, (_, i) => amb(`Game ${i}`)) }));
  const list = document.querySelector('.adm-details');
  assert.match(list.querySelector('summary').textContent, /\(1\)/);
  list.open = true; // the admin opens it to read
  await tick();
  await tick();
  assert.match(text('.adm-progress-txt')[0], /^5 \/ 512 juegos · Game/); // the bar did not wait for them to close it
  assert.equal(document.querySelector('.adm-details'), list); // the very same element: not redrawn
  assert.equal(list.open, true);
  assert.match(list.querySelector('summary').textContent, /\(1\)/);
  list.open = false; // closed: the next tick brings what was missing
  await tick();
  assert.match(document.querySelector('.adm-details summary').textContent, /\(3\)/);
});

test('the lists are redrawn only when they change', async () => {
  await open((n) => status({ processed: 3 + n, not_found: [{ game_id: 'a', name: 'Alpha' }] }));
  const list = document.querySelector('.adm-details');
  await tick();
  await tick();
  assert.equal(document.querySelector('.adm-details'), list);
});

test('when the run ends everything is shown, with its reason and the way to start another', async () => {
  await open((n) => (n < 2 ? status({ processed: 10 + n, ambiguous: [amb('A')] }) : status({ state: 'finished', processed: 512, stop_reason: 'completed', ambiguous: [amb('A'), amb('B')] })));
  document.querySelector('.adm-details').open = true;
  await tick();
  assert.ok(document.querySelector('#hlCancel'));
  await tick();
  assert.equal(document.querySelector('#hlCancel'), null);
  assert.ok(document.querySelector('#hlAgain'));
  assert.match(document.querySelector('.modal-content').textContent, /Terminada: se han procesado todos los juegos/);
  assert.match(document.querySelector('.adm-details summary').textContent, /\(2\)/); // even the one that was being read is brought up to date
  assert.equal(text('.adm-progress-txt')[0], '512 / 512 juegos');
});

test('the time left comes from the pace seen since the first poll, and says nothing before there is one', async () => {
  const { minutesLeft } = await import('../js/pages/admin/hltb-sync.js');
  const first = { at: 0, done: 3 };
  assert.equal(minutesLeft(first, { processed: 4, total: 512 }, 6000), null); // one game is not a pace
  assert.equal(minutesLeft(first, { processed: 5, total: 105 }, 10000), 9); // 2 games in 10 s: 100 left = 500 s, 8,3 min
  assert.equal(minutesLeft(first, { processed: 509, total: 512 }, 5000), 1); // never says 0
  assert.equal(minutesLeft(first, { processed: 9, total: 12 }, 0), null);
});

test('the figures say how long is left once the run has a pace', async () => {
  mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  let calls = 0;
  installApi({ 'GET /manage/hltb-sync/status': () => status({ processed: 3 + Math.max(0, calls++ - 1) * 2, total: 103 }) });
  await hltbSyncFlow({ onDone: () => {} });
  await settle();
  assert.doesNotMatch(text('.adm-progress-txt')[0], /quedan/);
  mock.timers.tick(2000);
  await settle();
  assert.match(text('.adm-progress-txt')[0], /5 \/ 103 juegos · Game · quedan unos 2 min/);
});
