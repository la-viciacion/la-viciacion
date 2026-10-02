import assert from 'node:assert/strict';
import { test } from 'node:test';
import { deviceLabel, needsInstall, subscriptionBody, urlBase64ToUint8Array } from '../js/lib/push.js';

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

test('deviceLabel names the browser and the system', () => {
  assert.equal(deviceLabel('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36'), 'Chrome · Android');
  assert.equal(deviceLabel('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36 Edg/126.0'), 'Edge · Windows');
  assert.equal(deviceLabel('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1'), 'Safari · iOS');
  assert.equal(deviceLabel('Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0'), 'Firefox · Linux');
  assert.equal(deviceLabel(null), 'Dispositivo');
});

test('needsInstall only for iOS outside the installed app', () => {
  const iphone = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1';
  assert.equal(needsInstall(iphone, false), true);
  assert.equal(needsInstall(iphone, true), false);
  assert.equal(needsInstall('Mozilla/5.0 (Linux; Android 14) Chrome/126.0', false), false);
});
