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

test('stopping a timer that another device already stopped refreshes the card', async () => {
  installApi({ 'GET /timers/active/7': RUNNING, 'POST /timers/stop/5': () => json({ detail: 'Active timer not found' }, 404) });
  await loadTimerCard();
  document.getElementById('stopTimerBtn').click();
  await settle();
  assert.equal(changes, 1);
});
