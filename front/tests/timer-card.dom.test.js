import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
installDom('<section id="timerSection"></section>');
const { initTimer, loadTimerCard, stopClock } = await import('../js/pages/home/timer.js');
const timerModule = await import('../js/pages/home/timer.js');

const RUNNING = { is_active: true, timer: { id: 5, game_id: 'hades', start_time: '2026-06-17T10:00:00' }, game_name: 'Hades', score: null };
let changes;

beforeEach(() => {
  changes = 0;
  initTimer({ userId: 7, onChange: async () => { changes += 1; }, onChoose: () => {}, onContinue: () => {} });
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
