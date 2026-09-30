import assert from 'node:assert/strict';
import { test } from 'node:test';
import { subscriptionBody, urlBase64ToUint8Array } from '../js/lib/push.js';

test('urlBase64ToUint8Array decodes base64url without padding', () => {
  // 65 bytes like a real VAPID public key: 0x04 followed by 64 more
  const bytes = Uint8Array.from([4, ...Array.from({ length: 64 }, (_, i) => i)]);
  const base64url = Buffer.from(bytes).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  assert.deepEqual(urlBase64ToUint8Array(base64url), bytes);
});

test('urlBase64ToUint8Array handles the url-safe alphabet', () => {
  assert.deepEqual(urlBase64ToUint8Array('-_8'), Uint8Array.from([0xfb, 0xff]));
});

test('subscriptionBody keeps only what the server needs', () => {
  const subscription = { toJSON: () => ({ endpoint: 'https://push.example/x', expirationTime: null, keys: { p256dh: 'P', auth: 'A' } }) };
  assert.deepEqual(subscriptionBody(subscription, false, 'UA'), {
    endpoint: 'https://push.example/x',
    keys: { p256dh: 'P', auth: 'A' },
    receive_group: false,
    user_agent: 'UA',
  });
  assert.equal(subscriptionBody(subscription, true).user_agent, null);
});
