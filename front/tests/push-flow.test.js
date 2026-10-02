import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { currentSubscription, enablePush, pushSupported, removeDevice, setReceiveGroup } from '../js/lib/push.js';

// the browser pieces the push flow touches
globalThis.localStorage = { getItem: () => 'tok', setItem() {}, removeItem() {} };
const realNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
const realFetch = globalThis.fetch;

let requests;
let subscription; // what pushManager holds for this device
let subscribed; // arguments of pushManager.subscribe
let permission;

function fakeSubscription(endpoint) {
  return {
    endpoint,
    toJSON: () => ({ endpoint, keys: { p256dh: 'P256', auth: 'AUTH' } }),
    unsubscribed: false,
    async unsubscribe() {
      this.unsubscribed = true;
    },
  };
}

function browser({ ready } = {}) {
  const registration = {
    pushManager: {
      getSubscription: async () => subscription,
      subscribe: async (options) => {
        subscribed = options;
        subscription = fakeSubscription('https://push.example/new');
        return subscription;
      },
    },
  };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: { userAgent: 'Mozilla/5.0 (Linux; Android 14) Chrome/126.0', serviceWorker: { ready: ready ?? Promise.resolve(registration) } },
  });
  globalThis.window = { PushManager: {}, Notification: {} };
  globalThis.Notification = { requestPermission: async () => permission };
}

beforeEach(() => {
  requests = [];
  subscription = null;
  subscribed = null;
  permission = 'granted';
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, body: options.body ? JSON.parse(options.body) : null, method: options.method });
    return new Response(JSON.stringify({ message: 'ok' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  browser();
});

afterEach(() => {
  globalThis.fetch = realFetch;
  Object.defineProperty(globalThis, 'navigator', realNavigator);
  delete globalThis.window;
  delete globalThis.Notification;
});

const PUBLIC_KEY = Buffer.from(Uint8Array.from([4, ...Array.from({ length: 64 }, (_, i) => i)])).toString('base64url');

test('push is supported only where the browser has a service worker, push and notifications', () => {
  assert.equal(pushSupported(), true);
  globalThis.window = { PushManager: {} }; // no Notification
  assert.equal(pushSupported(), false);
  globalThis.window = { PushManager: {}, Notification: {} };
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'x' } }); // no service worker
  assert.equal(pushSupported(), false);
});

test('the current subscription is whatever the push manager holds for this device', async () => {
  assert.equal(await currentSubscription(), null);
  subscription = fakeSubscription('https://push.example/mine');
  assert.equal((await currentSubscription()).endpoint, 'https://push.example/mine');
});

test('a browser that cannot answer is "no subscription", not an error', async () => {
  browser({ ready: Promise.reject(new Error('worker failed')) });
  assert.equal(await currentSubscription(), null);
});

test('a worker that never gets ready does not hang the page: it gives up after four seconds', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  browser({ ready: new Promise(() => {}) });
  const pending = currentSubscription();
  t.mock.timers.tick(4000);
  assert.equal(await pending, null);
});

test('enabling push subscribes this device with the server key and registers it', async () => {
  await enablePush({ publicKey: PUBLIC_KEY, receiveGroup: true });
  assert.equal(subscribed.userVisibleOnly, true);
  assert.deepEqual([...subscribed.applicationServerKey].slice(0, 3), [4, 0, 1]);
  assert.equal(subscribed.applicationServerKey.length, 65);
  const [{ url, method, body }] = requests;
  assert.equal(url, '/api/v1/push/subscribe');
  assert.equal(method, 'POST');
  assert.deepEqual(body, {
    endpoint: 'https://push.example/new',
    keys: { p256dh: 'P256', auth: 'AUTH' },
    receive_group: true,
    user_agent: 'Mozilla/5.0 (Linux; Android 14) Chrome/126.0',
  });
});

test('a device that is already subscribed is reused, not subscribed again', async () => {
  subscription = fakeSubscription('https://push.example/existing');
  await enablePush({ publicKey: PUBLIC_KEY, receiveGroup: false });
  assert.equal(subscribed, null);
  assert.equal(requests[0].body.endpoint, 'https://push.example/existing');
  assert.equal(requests[0].body.receive_group, false);
});

test('without permission nothing is subscribed or sent, and the reason is clear', async () => {
  permission = 'denied';
  await assert.rejects(enablePush({ publicKey: PUBLIC_KEY, receiveGroup: true }), { message: 'El permiso de notificaciones está denegado en el navegador' });
  assert.equal(subscribed, null);
  assert.deepEqual(requests, []);
});

test('a worker that never registers makes enabling fail with a message instead of hanging', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  browser({ ready: new Promise(() => {}) });
  const outcome = enablePush({ publicKey: PUBLIC_KEY, receiveGroup: true }).catch((error) => error);
  // two waits for the worker (the current subscription, then the registration), each gives up after four seconds
  for (let i = 0; i < 3; i++) {
    await new Promise((resolve) => setImmediate(resolve));
    t.mock.timers.tick(4000);
  }
  const error = await outcome;
  assert.equal(error.message, 'El navegador no ha podido activar el servicio de notificaciones');
  assert.deepEqual(requests, []);
});

test('removing a device tells the server and, if it is this very device, unsubscribes it in the browser too', async () => {
  subscription = fakeSubscription('https://push.example/this-one');
  await removeDevice('https://push.example/this-one');
  assert.deepEqual(requests[0], { url: '/api/v1/push/unsubscribe', method: 'POST', body: { endpoint: 'https://push.example/this-one' } });
  assert.equal(subscription.unsubscribed, true);
});

test('removing another device leaves this one subscribed', async () => {
  subscription = fakeSubscription('https://push.example/this-one');
  await removeDevice('https://push.example/the-tablet');
  assert.equal(requests.length, 1);
  assert.equal(subscription.unsubscribed, false);
});

test('removing a device in a browser without push only tells the server', async () => {
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'x' } });
  await removeDevice('https://push.example/x');
  assert.equal(requests.length, 1);
});

test('choosing whether a device receives the group notices is a PATCH', async () => {
  await setReceiveGroup('https://push.example/x', false);
  assert.deepEqual(requests[0], { url: '/api/v1/push/subscription', method: 'PATCH', body: { endpoint: 'https://push.example/x', receive_group: false } });
});
