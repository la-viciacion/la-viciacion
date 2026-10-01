import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../sw.js', import.meta.url), 'utf8');

/** Runs sw.js against a fake service worker scope and returns its handlers plus what it did. */
function load() {
  const handlers = {};
  const shown = [];
  const opened = [];
  const scope = {
    addEventListener: (type, fn) => (handlers[type] = fn),
    skipWaiting: () => {},
    registration: { showNotification: async (title, options) => shown.push({ title, ...options }) },
    clients: { claim: async () => {}, matchAll: async () => [], openWindow: async (url) => opened.push(url) },
    caches: { keys: async () => [], delete: async () => true },
  };
  scope.self = scope;
  vm.runInNewContext(source, scope);
  const run = async (type, event) => {
    let pending = Promise.resolve();
    await handlers[type]({ ...event, waitUntil: (p) => (pending = p) });
    await pending;
  };
  return { shown, opened, run };
}

const push = (payload) => ({ data: { json: () => payload } });

test('the running-timer notification is pinned and silent, and replaces the previous one', async () => {
  const sw = load();
  await sw.run('push', push({ title: 'Hollow Knight', body: '1h 25min', tag: 'timer', quiet: true, pinned: true, button: 'Parar', url: '/' }));
  const [n] = sw.shown;
  assert.equal(n.title, 'Hollow Knight');
  assert.equal(n.body, '1h 25min');
  assert.equal(n.tag, 'timer');
  assert.equal(n.silent, true);
  assert.equal(n.renotify, false); // Chrome rejects renotify together with silent
  assert.equal(n.requireInteraction, true);
  assert.deepEqual(JSON.parse(JSON.stringify(n.actions)), [{ action: 'open', title: 'Parar' }]);
});

test('the "stopped" notice that replaces it is quiet but no longer pinned', async () => {
  const sw = load();
  await sw.run('push', push({ title: 'Hollow Knight', body: 'Timer parado · 1h 25min', tag: 'timer', quiet: true }));
  assert.equal(sw.shown[0].silent, true);
  assert.equal(sw.shown[0].requireInteraction, false);
  assert.equal(sw.shown[0].actions, undefined);
});

test('a normal push with a tag still alerts again', async () => {
  const sw = load();
  await sw.run('push', push({ title: 'T', body: 'b', tag: 'group' }));
  assert.equal(sw.shown[0].renotify, true);
  assert.equal(sw.shown[0].silent, false);
  assert.equal(sw.shown[0].requireInteraction, false);
});

test('a push without data still shows something', async () => {
  const sw = load();
  await sw.run('push', {});
  assert.equal(sw.shown[0].title, 'La Viciación');
});

test('tapping a notification closes it and opens its url', async () => {
  const sw = load();
  const notification = { data: { url: '#/profile' }, close() { this.closed = true; } };
  await sw.run('notificationclick', { notification });
  assert.equal(notification.closed, true);
  assert.deepEqual(JSON.parse(JSON.stringify(sw.opened)), ['#/profile']);
});

test('tapping the button opens the app like tapping the notification', async () => {
  const sw = load();
  const notification = { data: { url: '/' }, close() {} };
  await sw.run('notificationclick', { action: 'open', notification });
  assert.deepEqual(JSON.parse(JSON.stringify(sw.opened)), ['/']);
});
