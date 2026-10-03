import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage } from './dom.js';

installStorage();
installDom();
const { current, refresh, startPresence, stopPresence, subscribe, summarize } = await import('../js/lib/presence.js');

const P = (id, extra = {}) => ({ user_id: id, name: `P${id}`, stale: false, ...extra });

afterEach(() => stopPresence());

test('the viewer never sees themselves in the list, and a stale timer is apart', () => {
  const s = summarize([P(1), P(2), P(3, { stale: true })], 1);
  assert.deepEqual(s.fresh.map((p) => p.user_id), [2]);
  assert.deepEqual(s.stale.map((p) => p.user_id), [3]);
  assert.equal(s.meActive, true);
});

test('the aura on the own avatar needs a timer that is running and not stale', () => {
  assert.equal(summarize([P(2)], 1).meActive, false);
  assert.equal(summarize([P(1, { stale: true })], 1).meActive, false);
});

test('a refresh stores the list and tells whoever subscribed, until they unsubscribe', async () => {
  installApi({ 'GET /timers/now-playing': [P(2)] });
  const seen = [];
  const off = subscribe((list) => seen.push(list.length));
  await refresh();
  assert.deepEqual(seen, [1]);
  assert.equal(current().length, 1);
  off();
  await refresh();
  assert.deepEqual(seen, [1]);
});

test('a failed refresh keeps what was on screen', async () => {
  installApi({ 'GET /timers/now-playing': [P(2)] });
  await refresh();
  globalThis.fetch = async () => { throw new Error('offline'); };
  await refresh();
  assert.equal(current().length, 1);
});

test('starting asks at once and stopping forgets the list', async () => {
  const calls = installApi({ 'GET /timers/now-playing': [P(2)] });
  startPresence();
  startPresence(); // idempotent
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls.length, 1);
  assert.equal(current().length, 1);
  stopPresence();
  assert.equal(current().length, 0);
});
