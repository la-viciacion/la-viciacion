import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

const window = installDom('', 'http://localhost/');
installStorage();
globalThis.location = window.location;
const { mountChat, unmountChat } = await import('../js/ui/chat.js');

afterEach(() => { unmountChat(); window.location.hash = ''; });

const q = (selector) => document.querySelector(selector);
const ask = async (text) => {
  q('.chat-input').value = text;
  q('.chat-form').requestSubmit();
  await settle();
};

test('without the chat on the API there is no button', async () => {
  installApi({ 'GET /chat/status': { available: false } });
  await mountChat();
  assert.equal(q('#chat-root'), null);
});

test('a failing status request leaves the page alone', async () => {
  installApi({ 'GET /chat/status': () => json({ detail: 'x' }, 500) });
  await mountChat();
  assert.equal(q('#chat-root'), null);
});

test('the button opens the panel with the suggestions and Escape closes it', async () => {
  installApi({ 'GET /chat/status': { available: true } });
  await mountChat();
  assert.ok(q('.chat-fab'));
  assert.ok(q('.chat-panel').hidden);
  q('.chat-fab').click();
  assert.equal(q('.chat-panel').hidden, false);
  assert.ok(q('.chat-chip'));
  document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape' }));
  assert.ok(q('.chat-panel').hidden);
  assert.equal(q('.chat-fab').hidden, false);
});

test('a question goes to the API with the history and the answer is shown, escaped', async () => {
  const calls = installApi({
    'GET /chat/status': { available: true },
    'POST /chat': ({ body }) => ({ answer: body.history.length ? 'Segunda' : '**Ana** va <b>primera</b>', in_scope: true }),
  });
  await mountChat();
  q('.chat-fab').click();
  await ask('¿Quién gana?');
  assert.equal(q('.chat-me').textContent, '¿Quién gana?');
  assert.equal(q('.chat-bot strong').textContent, 'Ana');
  assert.equal(q('.chat-bot b'), null); // the model's markup is text
  assert.equal(q('.chat-bot').textContent, 'Ana va <b>primera</b>');
  await ask('¿Y luego?');
  const posts = calls.filter((c) => c.method === 'POST');
  assert.deepEqual(posts[1].body.history.map((t) => t.role), ['user', 'assistant']);
});

test('a failed question shows the error and is not sent again as history', async () => {
  let fail = true;
  const calls = installApi({
    'GET /chat/status': { available: true },
    'POST /chat': () => (fail ? json({ detail: 'El asistente no ha podido responder' }, 502) : { answer: 'Ya', in_scope: true }),
  });
  await mountChat();
  q('.chat-fab').click();
  await ask('hola');
  assert.equal(q('.chat-error').textContent, 'El asistente no ha podido responder');
  fail = false;
  await ask('otra vez');
  assert.deepEqual(calls.filter((c) => c.method === 'POST')[1].body.history, []);
});

test('a suggestion asks it, and the new conversation button empties the chat', async () => {
  installApi({ 'GET /chat/status': { available: true }, 'POST /chat': { answer: 'ok', in_scope: true } });
  await mountChat();
  q('.chat-fab').click();
  q('.chat-chip').click();
  await settle();
  assert.equal(document.querySelectorAll('.chat-msg').length, 2);
  q('[data-reset]').click();
  assert.equal(document.querySelectorAll('.chat-msg').length, 0);
  assert.ok(q('.chat-chip'));
});

test('it hides on the story and comes back, and logging out removes it', async () => {
  installApi({ 'GET /chat/status': { available: true } });
  await mountChat();
  window.location.hash = '#/story';
  window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  assert.equal(q('#chat-root').hidden, true);
  window.location.hash = '';
  window.dispatchEvent(new window.HashChangeEvent('hashchange'));
  assert.equal(q('#chat-root').hidden, false);
  unmountChat();
  assert.equal(q('#chat-root'), null);
});
