import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { loadPlatforms, platformList, platformName } from '../js/lib/platforms.js';

const storage = new Map();
globalThis.localStorage = {
  getItem: (key) => (storage.has(key) ? storage.get(key) : null),
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
};

const realFetch = globalThis.fetch;
const realError = console.error;
let asked;

beforeEach(() => {
  asked = [];
  console.error = () => {};
});

afterEach(() => {
  globalThis.fetch = realFetch;
  console.error = realError;
});

const answering = (response) => {
  globalThis.fetch = async (url) => {
    asked.push(url);
    return response.clone();
  };
};

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

test('the catalogue is loaded from the API and shared', async () => {
  answering(json([{ id: 'pc', name: 'PC' }, { id: 'switch', name: 'Nintendo Switch' }]));
  assert.deepEqual(await loadPlatforms(), [{ id: 'pc', name: 'PC' }, { id: 'switch', name: 'Nintendo Switch' }]);
  assert.equal(asked[0], '/api/v1/utils/platforms');
  assert.deepEqual(platformList(), [{ id: 'pc', name: 'PC' }, { id: 'switch', name: 'Nintendo Switch' }]);
});

test('a platform shows its name, or its id when the catalogue does not know it', async () => {
  answering(json([{ id: 'pc', name: 'PC' }]));
  await loadPlatforms();
  assert.equal(platformName('pc'), 'PC');
  assert.equal(platformName('atari-lynx'), 'atari-lynx');
  assert.equal(platformName(null), null);
});

test('a failing request keeps the previous catalogue and does not throw', async () => {
  answering(json([{ id: 'pc', name: 'PC' }]));
  await loadPlatforms();
  answering(json({ detail: 'down' }, 500));
  assert.deepEqual(await loadPlatforms(), [{ id: 'pc', name: 'PC' }]);
});

test('a session that expired while loading leaves an empty catalogue instead of failing', async () => {
  answering(json({ detail: 'Could not validate credentials' }, 401));
  assert.deepEqual(await loadPlatforms(), []);
});
