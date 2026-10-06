import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { API_BASE, api, forgetAvatars, jsonRequest, loadAvatarUrl, login, session, setUnauthorizedHandler } from '../js/lib/api.js';

// the browser's localStorage and fetch, as far as the client uses them
const storage = new Map();
globalThis.localStorage = {
  getItem: (key) => (storage.has(key) ? storage.get(key) : null),
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
};

let calls;
let answer;
const realFetch = globalThis.fetch;

beforeEach(() => {
  storage.clear();
  calls = [];
  setUnauthorizedHandler(() => {});
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return typeof answer === 'function' ? answer(url, options) : answer.clone(); // a Response body can be read once
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

test('the token is kept in the browser and can be dropped', () => {
  assert.equal(session.getToken(), null);
  session.setToken('abc');
  assert.equal(session.getToken(), 'abc');
  session.clear();
  assert.equal(session.getToken(), null);
});

test('jsonRequest builds a request with a JSON body', () => {
  assert.deepEqual(jsonRequest('PATCH', { a: 1 }), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: '{"a":1}' });
});

test('a request goes under /api/v1 and carries the token when there is one', async () => {
  answer = json({ ok: true });
  assert.deepEqual(await api('/users/ana'), { ok: true });
  assert.equal(calls[0].url, `${API_BASE}/users/ana`);
  assert.equal(calls[0].options.headers.Authorization, undefined);
  session.setToken('tok');
  await api('/users/ana');
  assert.equal(calls[1].options.headers.Authorization, 'Bearer tok');
});

test('the options of the caller are kept and its own headers are not lost', async () => {
  answer = json({});
  session.setToken('tok');
  await api('/timers/start', { ...jsonRequest('POST', { game_id: 'x' }), headers: { 'Content-Type': 'application/json', 'X-Extra': '1' } });
  const { options } = calls[0];
  assert.equal(options.method, 'POST');
  assert.equal(options.body, '{"game_id":"x"}');
  assert.deepEqual(options.headers, { 'Content-Type': 'application/json', 'X-Extra': '1', Authorization: 'Bearer tok' });
});

test('the answer is read according to its content type', async () => {
  answer = json([1, 2]);
  assert.deepEqual(await api('/x'), [1, 2]);
  answer = new Response('plain', { status: 200, headers: { 'Content-Type': 'text/plain' } });
  assert.equal(await api('/x'), 'plain');
  answer = new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { 'Content-Type': 'image/png' } });
  const blob = await api('/x');
  assert.ok(blob instanceof Blob);
  assert.equal(blob.size, 3);
});

test('a 401 forgets the session, tells the router and answers null', async () => {
  session.setToken('expired');
  let told = 0;
  setUnauthorizedHandler(() => told++);
  answer = json({ detail: 'Could not validate credentials' }, 401);
  assert.equal(await api('/users/ana'), null);
  assert.equal(session.getToken(), null);
  assert.equal(told, 1);
});

test('an error carries the status, the detail and a readable message', async () => {
  const cases = [
    [{ detail: 'El usuario ya existe' }, 409, 'El usuario ya existe'],
    [{ detail: [{ msg: 'campo requerido' }, { msg: 'valor no válido' }] }, 422, 'campo requerido; valor no válido'],
    [{ detail: { message: 'Tiene datos asociados', counts: { sesiones: 3 } } }, 409, 'Tiene datos asociados'],
    [{ detail: {} }, 500, 'HTTP 500'],
  ];
  for (const [body, status, message] of cases) {
    answer = json(body, status);
    await assert.rejects(api('/x'), (error) => {
      assert.equal(error.message, message);
      assert.equal(error.status, status);
      assert.deepEqual(error.detail, body.detail);
      return true;
    });
  }
});

test('an error without a JSON body still says something', async () => {
  answer = new Response('<html>Bad gateway</html>', { status: 502, headers: { 'Content-Type': 'text/html' } });
  await assert.rejects(api('/x'), { message: 'Error desconocido', status: 502 });
});

test('the 409 of a delete that needs confirmation keeps its list of what would be lost', async () => {
  answer = json({ detail: { message: 'Tiene datos asociados', counts: { sesiones: 2, biblioteca: 1 } } }, 409);
  await assert.rejects(api('/manage/users/3', { method: 'DELETE' }), (error) => {
    assert.deepEqual(error.detail.counts, { sesiones: 2, biblioteca: 1 });
    return true;
  });
});

test('login posts the credentials as a form and keeps the token', async () => {
  answer = json({ access_token: 'jwt-1', token_type: 'bearer' });
  await login('ana', 'p@ss word');
  const { url, options } = calls[0];
  assert.equal(url, `${API_BASE}/token`);
  assert.equal(options.method, 'POST');
  assert.equal(options.headers['Content-Type'], 'application/x-www-form-urlencoded');
  assert.equal(options.body.toString(), 'username=ana&password=p%40ss+word');
  assert.equal(session.getToken(), 'jwt-1');
});

test('a refused login says why, or falls back to a generic message, and stores nothing', async () => {
  answer = json({ detail: 'Demasiados intentos fallidos. Vuelve a intentarlo en 15 min' }, 429);
  await assert.rejects(login('ana', 'x'), { message: 'Demasiados intentos fallidos. Vuelve a intentarlo en 15 min' });
  answer = new Response('boom', { status: 500 });
  await assert.rejects(login('ana', 'x'), { message: 'Usuario o contraseña incorrectos' });
  assert.equal(session.getToken(), null);
});

test('the avatar is an object URL, or null when the user has none', async () => {
  const realCreate = URL.createObjectURL;
  URL.createObjectURL = (blob) => `blob:fake/${blob.size}`;
  try {
    answer = new Response(new Uint8Array([1, 2, 3, 4]), { status: 200, headers: { 'Content-Type': 'image/png' } });
    assert.equal(await loadAvatarUrl('ana'), 'blob:fake/4');
    assert.equal(calls[0].url, `${API_BASE}/users/ana/avatar`);
    answer = json({ detail: 'Avatar not found' }, 404);
    assert.equal(await loadAvatarUrl('bea'), null);
    answer = new Response(new Uint8Array([]), { status: 200, headers: { 'Content-Type': 'image/png' } });
    assert.equal(await loadAvatarUrl('cai'), null); // an empty picture is no picture
    answer = json({}, 200);
    assert.equal(await loadAvatarUrl('dan'), null); // not an image at all
  } finally {
    URL.createObjectURL = realCreate;
  }
});

test('an avatar is asked for once until it is forgotten', async () => {
  answer = json({}, 404);
  await loadAvatarUrl('eva');
  await loadAvatarUrl('eva');
  assert.equal(calls.length, 1);
  forgetAvatars();
  await loadAvatarUrl('eva');
  assert.equal(calls.length, 2);
});

test('the username of the avatar request is encoded', async () => {
  answer = json({}, 404);
  await loadAvatarUrl('a/b c');
  assert.equal(calls[0].url, `${API_BASE}/users/a%2Fb%20c/avatar`);
});
