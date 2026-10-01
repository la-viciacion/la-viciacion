import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../sw.js', import.meta.url), 'utf8');

/** Runs sw.js against a fake service worker scope and returns its handlers plus what it did. */
function load({ fetchResult } = {}) {
  const handlers = {};
  const shown = [];
  const calls = { fetch: [], focus: 0, opened: [] };
  const scope = {
    addEventListener: (type, fn) => (handlers[type] = fn),
    skipWaiting: () => {},
    registration: { showNotification: async (title, options) => shown.push({ title, ...options }) },
    clients: {
      claim: async () => {},
      matchAll: async () => [],
      openWindow: async (url) => calls.opened.push(url),
    },
    caches: { keys: async () => [], delete: async () => true },
    fetch: async (url, init) => {
      calls.fetch.push({ url, init });
      if (fetchResult instanceof Error) throw fetchResult;
      return fetchResult || { ok: true };
    },
  };
  scope.self = scope;
  vm.runInNewContext(source, scope);
  const run = async (type, event) => {
    let pending = Promise.resolve();
    await handlers[type]({ ...event, waitUntil: (p) => (pending = p) });
    await pending;
  };
  return { shown, calls, run };
}

// arrays made inside the vm context have another prototype: compare plain copies
const plain = (value) => JSON.parse(JSON.stringify(value));
const minutesAgo = (n) => Date.now() - n * 60000;
const timerPush = (extra = {}) => ({ data: { json: () => ({ kind: 'timer', title: 'Hollow Knight', body: '1h 25min', tag: 'timer', quiet: true, start: minutesAgo(85), token: 'T', url: '/', ...extra }) } });
const click = (data, action = '') => ({ action, notification: { data, close() { this.closed = true; } } });
const timerData = (extra = {}) => ({ kind: 'timer', game: 'Hollow Knight', start: minutesAgo(85), token: 'T', url: '/', ...extra });

test('a timer push is a pinned, silent notification with a stop button', async () => {
  const sw = load();
  await sw.run('push', timerPush());
  const [n] = sw.shown;
  assert.equal(n.title, 'Hollow Knight');
  assert.equal(n.body, '1h 25min');
  assert.equal(n.tag, 'timer');
  assert.equal(n.silent, true);
  assert.equal(n.requireInteraction, true);
  assert.deepEqual(plain(n.actions), [{ action: 'stop', title: 'Parar' }]);
  assert.equal(n.data.token, 'T');
});

test('a quiet push never asks to alert again (Chrome rejects silent with renotify)', async () => {
  const sw = load();
  await sw.run('push', { data: { json: () => ({ title: 'Hollow Knight', body: 'Timer parado · 1h 25min', tag: 'timer', quiet: true }) } });
  assert.equal(sw.shown[0].silent, true);
  assert.equal(sw.shown[0].renotify, false);
});

test('a normal push with a tag still alerts again', async () => {
  const sw = load();
  await sw.run('push', { data: { json: () => ({ title: 'T', body: 'b', tag: 'group' }) } });
  assert.equal(sw.shown[0].renotify, true);
  assert.equal(sw.shown[0].silent, false);
});

test('"Parar" asks for confirmation instead of stopping', async () => {
  const sw = load();
  await sw.run('notificationclick', click(timerData(), 'stop'));
  assert.equal(sw.calls.fetch.length, 0);
  const [n] = sw.shown;
  assert.match(n.body, /^¿Parar el timer\? Llevas 1h 25min$/);
  assert.equal(n.tag, 'timer');
  assert.deepEqual(plain(n.actions).map((a) => a.action), ['confirm-stop', 'cancel']);
});

test('"Cancelar" puts the timer notification back with the time computed on the device', async () => {
  const sw = load();
  await sw.run('notificationclick', click(timerData(), 'cancel'));
  assert.equal(sw.calls.fetch.length, 0);
  assert.equal(sw.shown[0].body, '1h 25min');
  assert.deepEqual(plain(sw.shown[0].actions), [{ action: 'stop', title: 'Parar' }]);
});

test('"Sí, parar" sends the token and leaves a "stopped" notification that is not pinned', async () => {
  const sw = load();
  await sw.run('notificationclick', click(timerData(), 'confirm-stop'));
  const [{ url, init }] = sw.calls.fetch;
  assert.equal(url, '/api/v1/push/stop-timer');
  assert.equal(init.method, 'POST');
  assert.deepEqual(JSON.parse(init.body), { token: 'T' });
  const [n] = sw.shown;
  assert.equal(n.body, 'Timer parado · 1h 25min');
  assert.equal(n.tag, 'timer');
  assert.equal(n.requireInteraction, undefined);
  assert.equal(n.actions, undefined);
});

test('a timer stopped a few seconds after starting just says it stopped', async () => {
  const sw = load();
  await sw.run('notificationclick', click(timerData({ start: Date.now() - 10000 }), 'confirm-stop'));
  assert.equal(sw.shown[0].body, 'Timer parado');
});

test('if the token was rejected the timer notification stays and the app opens', async () => {
  const sw = load({ fetchResult: { ok: false, status: 401 } });
  await sw.run('notificationclick', click(timerData(), 'confirm-stop'));
  assert.equal(sw.shown.length, 1);
  assert.deepEqual(plain(sw.shown[0].actions), [{ action: 'stop', title: 'Parar' }]);
  assert.deepEqual(plain(sw.calls.opened), ['/']);
});

test('without network the timer notification stays and the app opens', async () => {
  const sw = load({ fetchResult: new TypeError('Failed to fetch') });
  await sw.run('notificationclick', click(timerData(), 'confirm-stop'));
  assert.equal(sw.shown.length, 1);
  assert.deepEqual(plain(sw.calls.opened), ['/']);
});

test('tapping the body of any notification opens its url', async () => {
  const sw = load();
  const event = click({ url: '#/profile' });
  await sw.run('notificationclick', event);
  assert.equal(event.notification.closed, true);
  assert.deepEqual(plain(sw.calls.opened), ['#/profile']);
  const timer = click(timerData());
  await sw.run('notificationclick', timer);
  assert.deepEqual(plain(sw.calls.opened), ['#/profile', '/']);
});

test('the elapsed text matches the server: under a minute, minutes, hours', async () => {
  const sw = load();
  for (const [minutes, text] of [[0, 'Timer iniciado'], [1, '1 min'], [59, '59 min'], [60, '1h 00min'], [605, '10h 05min']]) {
    sw.shown.length = 0;
    await sw.run('notificationclick', click(timerData({ start: Date.now() - minutes * 60000 - 500 }), 'cancel'));
    assert.equal(sw.shown[0].body, text);
  }
});
