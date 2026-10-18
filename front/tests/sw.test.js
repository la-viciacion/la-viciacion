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
  const on = { screen: [], windows: [] }; // notifications the fake browser is showing, and the windows of the app that are open
  const scope = {
    addEventListener: (type, fn) => (handlers[type] = fn),
    skipWaiting: () => {},
    registration: {
      scope: 'https://viciacion.example/',
      showNotification: async (title, options) => shown.push({ title, ...options }),
      getNotifications: async ({ tag }) => on.screen.filter((n) => n.tag === tag),
    },
    clients: { claim: async () => {}, matchAll: async () => on.windows, openWindow: async (url) => opened.push(url) },
    caches: { keys: async () => [], delete: async () => true },
    URL, // a real service worker has it; the bare vm context does not
  };
  scope.self = scope;
  vm.runInNewContext(source, scope);
  const run = async (type, event) => {
    let pending = Promise.resolve();
    await handlers[type]({ ...event, waitUntil: (p) => (pending = p) });
    await pending;
  };
  return { shown, opened, run, on };
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

test('a quiet refresh closes the notification it replaces (iOS piles them up otherwise)', async () => {
  const sw = load();
  const old = { tag: 'timer', close() { this.closed = true; } };
  const other = { tag: 'group', close() { this.closed = true; } };
  sw.on.screen.push(old, other);
  await sw.run('push', push({ title: 'Hollow Knight', body: '9 min', tag: 'timer', quiet: true, pinned: true }));
  assert.equal(old.closed, true);
  assert.equal(other.closed, undefined);
  assert.equal(sw.shown.length, 1);
});

test('a normal notice does not close anything', async () => {
  const sw = load();
  const old = { tag: 'group', close() { this.closed = true; } };
  sw.on.screen.push(old);
  await sw.run('push', push({ title: 'T', body: 'b', tag: 'group' }));
  assert.equal(old.closed, undefined);
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

test('tapping a pinned notification opens the app and shows it again', async () => {
  const sw = load();
  await sw.run('push', push({ title: 'Hollow Knight', body: '1h 25min', tag: 'timer', quiet: true, pinned: true, button: 'Parar', url: '/' }));
  const shown = sw.shown.pop();
  const notification = { title: shown.title, data: shown.data, close() { this.closed = true; } };
  await sw.run('notificationclick', { action: '', notification });
  assert.deepEqual(JSON.parse(JSON.stringify(sw.opened)), ['https://viciacion.example/']);
  assert.notEqual(notification.closed, true);
  const [again] = sw.shown;
  assert.deepEqual(JSON.parse(JSON.stringify({ ...again, data: undefined })), JSON.parse(JSON.stringify({ ...shown, data: undefined })));
  assert.equal(again.requireInteraction, true);
  assert.equal(again.silent, true);
});

test('tapping the button of a pinned notification keeps it too', async () => {
  const sw = load();
  const data = { url: '/', body: '5 min', tag: 'timer', quiet: true, pinned: true, button: 'Parar' };
  await sw.run('notificationclick', { action: 'open', notification: { title: 'Hollow Knight', data, close() {} } });
  assert.equal(sw.shown.length, 1);
  assert.equal(sw.shown[0].title, 'Hollow Knight');
  assert.equal(sw.shown[0].body, '5 min');
});

test('tapping an ordinary notification closes it and opens its url', async () => {
  const sw = load();
  const notification = { data: { url: '#/profile' }, close() { this.closed = true; } };
  await sw.run('notificationclick', { notification });
  assert.equal(notification.closed, true);
  assert.deepEqual(JSON.parse(JSON.stringify(sw.opened)), ['https://viciacion.example/#/profile']);
});

test('tapping the button opens the app like tapping the notification', async () => {
  const sw = load();
  const notification = { data: { url: '/' }, close() {} };
  await sw.run('notificationclick', { action: 'open', notification });
  assert.equal(sw.shown.length, 0);
  assert.deepEqual(JSON.parse(JSON.stringify(sw.opened)), ['https://viciacion.example/']);
});

test('tapping a notice while the app is open takes that window to the page', async () => {
  const sw = load();
  const calls = [];
  const client = { focus: async () => client, navigate: async (url) => calls.push(['navigate', url]) };
  sw.on.windows.push(client);
  await sw.run('notificationclick', { notification: { data: { url: '#/story/2026-09' }, close() {} } });
  assert.deepEqual(calls, [['navigate', 'https://viciacion.example/#/story/2026-09']]);
  assert.deepEqual(sw.opened, [], 'no second window');
});

test('an open app is only brought to the front when the notice has no page', async () => {
  const sw = load();
  const calls = [];
  const client = { focus: async () => { calls.push('focus'); return client; }, navigate: async () => calls.push('navigate') };
  sw.on.windows.push(client);
  await sw.run('notificationclick', { notification: { data: { url: '/' }, close() {} } });
  assert.deepEqual(calls, ['focus']);
});

test('if the open window cannot be taken to the page, a new one opens there', async () => {
  const sw = load();
  const client = { focus: async () => client, navigate: async () => { throw new Error('not controlled'); } };
  sw.on.windows.push(client);
  await sw.run('notificationclick', { notification: { data: { url: '#/story/2026-09' }, close() {} } });
  assert.deepEqual(sw.opened, ['https://viciacion.example/#/story/2026-09']);
});
