import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<section id="timerSection"></section>');
const { initTimer, loadTimerCard, stopClock } = await import('../js/pages/home/timer.js');
const timerModule = await import('../js/pages/home/timer.js');
const { forgetConversations } = await import('../js/lib/guide.js');

const RUNNING = { is_active: true, timer: { id: 5, game_id: 'hades', start_time: '2026-06-17T10:00:00' }, game_name: 'Hades', score: null };
let changes;
let chosen;
let continued;
let manual;

beforeEach(() => {
  forgetConversations();
  changes = 0;
  chosen = 0;
  continued = null;
  manual = 0;
  initTimer({
    userId: 7, onChange: async () => { changes += 1; }, onChoose: () => { chosen += 1; }, onContinue: (g) => { continued = g; }, onManual: () => { manual += 1; },
  });
  document.getElementById('timerSection').replaceChildren();
});

afterEach(() => stopClock());

test('a running timer shows its card with the clock', async () => {
  installApi({ 'GET /timers/active/7': RUNNING });
  await loadTimerCard();
  assert.equal(timerModule.hasActive, true);
  assert.ok(document.getElementById('stopTimerBtn'));
  assert.deepEqual(text('.timer-game'), ['Hades']);
});

test('a failed check is not "no timer": it says it could not check and offers to retry', async () => {
  installApi({ 'GET /timers/active/7': () => json({ detail: 'down' }, 503) });
  await loadTimerCard();
  assert.equal(timerModule.hasActive, false);
  assert.equal(document.getElementById('chooseGameBtn'), null); // no "Nuevo timer" over a timer that may be running
  assert.match(document.querySelector('.timer-idle-title').textContent, /No se ha podido comprobar/);
  document.getElementById('retryTimerBtn').click();
  assert.equal(changes, 1);
});

test('a running timer stays on screen when a later check fails', async () => {
  installApi({ 'GET /timers/active/7': RUNNING });
  await loadTimerCard();
  installApi({ 'GET /timers/active/7': () => json({ detail: 'down' }, 503) });
  await loadTimerCard();
  assert.equal(timerModule.hasActive, true);
  assert.ok(document.getElementById('stopTimerBtn'));
});

test('the start of a running timer is shown and can be moved back without stopping it', async () => {
  let sent = null;
  installApi({
    'GET /timers/active/7': RUNNING,
    'PATCH /timers/5/start': (req) => { sent = req; return json({ id: 5 }); },
  });
  await loadTimerCard();
  assert.match(document.getElementById('editStartBtn').textContent, /10:00/);
  document.getElementById('editStartBtn').click();
  const form = document.querySelector('.sess-form');
  const earlier = new Date(Date.now() - 3600 * 1000);
  const pad = (n) => String(n).padStart(2, '0');
  form.querySelector('[name="start"]').value = `${earlier.getFullYear()}-${pad(earlier.getMonth() + 1)}-${pad(earlier.getDate())}T${pad(earlier.getHours())}:${pad(earlier.getMinutes())}`;
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.ok(sent);
  assert.equal(changes, 1);
});

test('stopping a timer that another device already stopped refreshes the card', async () => {
  installApi({ 'GET /timers/active/7': RUNNING, 'POST /timers/stop/5': () => json({ detail: 'Active timer not found' }, 404) });
  await loadTimerCard();
  document.getElementById('stopTimerBtn').click();
  await settle();
  assert.equal(changes, 1);
});

const LAST = { game_id: 'factorio', game_name: 'Factorio', image_url: null, last_played: '2026-06-10T20:00:00', total_seconds: 4740, session_count: 3, score: null };
const NO_TIMER = { is_active: false };

test('with a latest game the card only continues it, and "Nuevo timer" and "Sesión manual" are in the row under it', async () => {
  installApi({ 'GET /timers/active/7': NO_TIMER, 'GET /timers/history/7/grouped': { groups: [LAST], total_games: 1 } });
  await loadTimerCard();
  assert.deepEqual(text('.timer-resume button'), ['Continuar']); // nothing else in the card
  assert.deepEqual(text('.home-actions button'), ['Nuevo timer', 'Sesión manual']);
  assert.equal(document.querySelector('.timer-resume').nextElementSibling, document.querySelector('.home-actions')); // right under it
  document.getElementById('continueGameBtn').click();
  document.getElementById('chooseGameBtn').click();
  document.getElementById('manualSessionBtn').click();
  assert.equal(continued.game_id, 'factorio');
  assert.equal(chosen, 1);
  assert.equal(manual, 1);
});

test('without a latest game the card is the "Nuevo timer" button and the row only has the manual session', async () => {
  installApi({ 'GET /timers/active/7': NO_TIMER, 'GET /timers/history/7/grouped': { groups: [], total_games: 0 } });
  await loadTimerCard();
  assert.deepEqual(text('.timer-idle button'), ['Nuevo timer']);
  assert.deepEqual(text('.home-actions button'), ['Sesión manual']);
  assert.equal(document.querySelectorAll('#chooseGameBtn').length, 1);
  document.getElementById('chooseGameBtn').click();
  document.getElementById('manualSessionBtn').click();
  assert.equal(chosen, 1);
  assert.equal(manual, 1);
});

test('while a timer runs, or when it cannot be checked, there is no row: neither a new timer nor a manual session can start', async () => {
  installApi({ 'GET /timers/active/7': RUNNING });
  await loadTimerCard();
  assert.equal(document.querySelector('.home-actions'), null);
  assert.equal(document.getElementById('manualSessionBtn'), null);
  installApi({ 'GET /timers/active/7': () => json({ detail: 'down' }, 503) });
  document.getElementById('timerSection').replaceChildren();
  timerModule.initTimer({ userId: 7, onChange: async () => {}, onChoose: () => {}, onContinue: () => {}, onManual: () => {} });
  await loadTimerCard();
  assert.equal(document.querySelector('.home-actions'), null);
});

test('the guide button stays hidden when the API says the guide is off', async () => {
  installApi({ 'GET /timers/active/7': RUNNING, 'GET /guide/status': { available: false } });
  await loadTimerCard();
  await settle();
  assert.equal(document.getElementById('timerGuideBtn').hidden, true);
});

test('the guide button shows when the guide is on and opens it for the game being played', async () => {
  installApi({ 'GET /timers/active/7': RUNNING, 'GET /guide/status': { available: true } });
  await loadTimerCard();
  await settle();
  const button = document.getElementById('timerGuideBtn');
  assert.equal(button.hidden, false);
  button.click();
  await settle();
  const dialog = document.querySelector('.modal-overlay');
  assert.match(dialog.querySelector('h3').textContent, /Guía: Hades/);
  assert.ok(dialog.querySelector('.gd-modal textarea.chat-input'), 'the box to ask is there without pressing anything else');
  assert.equal(dialog.querySelector('.section-title'), null);
  dialog.querySelector('[data-close]').click();
});

test('a guide that cannot be checked is simply not offered', async () => {
  installApi({ 'GET /timers/active/7': RUNNING, 'GET /guide/status': () => json({ detail: 'down' }, 503) });
  await loadTimerCard();
  await settle();
  assert.equal(document.getElementById('timerGuideBtn').hidden, true);
});
