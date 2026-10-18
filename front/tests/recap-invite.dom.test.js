import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>', 'http://localhost/');
globalThis.location = window.location;
const { dismissRecapInvite, inviteToRecap, recapCard } = await import('../js/ui/recap-invite.js');
const { hasSeen } = await import('../js/lib/recap-window.js');
const { html, mount } = await import('../js/lib/html.js');

const ANA = { id: 1, username: 'ana' };
const EARLY = new Date(2026, 9, 3); // 3 October: September is on offer
const LATE = new Date(2026, 9, 18);
const played = (seconds) => ({ 'GET /statistics/recap/2026-09?username=ana': { player: { seconds } } });
const bar = () => document.querySelector('.recap-invite');

function reset() {
  document.querySelectorAll('.recap-invite').forEach((el) => el.remove());
  for (const period of ['2026-09', '2026', '2026-12']) localStorage.removeItem(`lv-recap-seen-${period}`);
  window.location.hash = '#/';
}

test('on the first days it shows a bar that opens the story, once', async () => {
  reset();
  const calls = installApi(played(3600));
  await inviteToRecap(ANA, EARLY);
  assert.equal(calls[0].path, '/statistics/recap/2026-09?username=ana');
  assert.match(bar().textContent, /Ya está disponible tu resumen de septiembre de 2026/);
  assert.equal(bar().querySelector('a').getAttribute('href'), '#/story/2026-09');
  bar().querySelector('a').click();
  assert.equal(bar(), null, 'opening it removes it');
  assert.equal(hasSeen('2026-09'), true);
  await inviteToRecap(ANA, EARLY);
  assert.equal(bar(), null, 'and it does not come back');
});

test('closing it counts as seeing it', async () => {
  reset();
  installApi(played(3600));
  await inviteToRecap(ANA, EARLY);
  bar().querySelector('[data-act="close"]').click();
  assert.equal(bar(), null);
  assert.equal(hasSeen('2026-09'), true);
});

test('after the first days nothing is shown and nothing is asked', async () => {
  reset();
  const calls = installApi(played(3600));
  await inviteToRecap(ANA, LATE);
  assert.equal(bar(), null);
  assert.equal(calls.length, 0);
});

test('a player who did not play that month is not told about it', async () => {
  reset();
  installApi(played(0));
  await inviteToRecap(ANA, EARLY);
  assert.equal(bar(), null);
});

test('on the story page there is no bar, and opening the story clears it', async () => {
  reset();
  window.location.hash = '#/story/2026-09';
  const calls = installApi(played(3600));
  await inviteToRecap(ANA, EARLY);
  assert.equal(bar(), null);
  assert.equal(calls.length, 0);
  window.location.hash = '#/';
  await inviteToRecap(ANA, EARLY);
  assert.notEqual(bar(), null);
  dismissRecapInvite('2026-09');
  assert.equal(bar(), null);
  assert.equal(hasSeen('2026-09'), true);
});

test('there is one bar at a time', async () => {
  reset();
  installApi(played(3600));
  await Promise.all([inviteToRecap(ANA, EARLY), settle().then(() => inviteToRecap(ANA, EARLY))]);
  assert.equal(document.querySelectorAll('.recap-invite').length, 1);
});

test('the profile card is there during the first days, whatever was seen, and links to the story and the data', () => {
  reset();
  localStorage.setItem('lv-recap-seen-2026-09', '1');
  mount(document.getElementById('main'), html`${recapCard(EARLY)}`);
  const card = document.querySelector('.recap-card');
  assert.equal(document.querySelectorAll('.recap-card').length, 1);
  assert.match(card.textContent, /Tu resumen de septiembre de 2026 ya está disponible/);
  assert.deepEqual([...card.querySelectorAll('a')].map((a) => a.getAttribute('href')), ['#/story/2026-09', '#/recap/2026-09']);
  assert.equal(String(recapCard(LATE)), '');
});

test('in January the season is offered first and December the next time, and the profile has both', async () => {
  reset();
  const JANUARY = new Date(2027, 0, 3);
  const calls = installApi({
    'GET /statistics/recap/2026?username=ana': { player: { seconds: 3600 } },
    'GET /statistics/recap/2026-12?username=ana': { player: { seconds: 3600 } },
  });
  await inviteToRecap(ANA, JANUARY);
  assert.match(bar().textContent, /resumen de temporada 2026/);
  assert.equal(bar().querySelector('a').getAttribute('href'), '#/story/2026');
  assert.deepEqual(calls.map((c) => c.path), ['/statistics/recap/2026?username=ana']);
  bar().querySelector('a').click();
  await inviteToRecap(ANA, JANUARY);
  assert.match(bar().textContent, /resumen de diciembre de 2026/);
  mount(document.getElementById('main'), html`${recapCard(JANUARY)}`);
  assert.deepEqual([...document.querySelectorAll('.recap-card')].map((c) => c.dataset.period), ['2026', '2026-12']);
});

test('in January, if the season is not worth a notice (nothing played) December still is', async () => {
  reset();
  installApi({
    'GET /statistics/recap/2026?username=ana': { player: { seconds: 0 } },
    'GET /statistics/recap/2026-12?username=ana': { player: { seconds: 3600 } },
  });
  await inviteToRecap(ANA, new Date(2027, 0, 3));
  assert.match(bar().textContent, /diciembre de 2026/);
});
