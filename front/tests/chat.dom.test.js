import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

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

test('three suggestions are offered, and a new conversation offers others', async () => {
  installApi({ 'GET /chat/status': { available: true }, 'POST /chat': { answer: 'ok', in_scope: true } });
  await mountChat();
  q('.chat-fab').click();
  const first = text('.chat-chip');
  assert.equal(first.length, 3);
  assert.equal(new Set(first).size, 3);
  // a conversation started: the chips are gone; reset and they come back, chosen again
  q('.chat-chip').click();
  await settle();
  assert.equal(document.querySelectorAll('.chat-chip').length, 0);
  const seen = new Set(first);
  for (let i = 0; i < 20; i++) {
    q('[data-reset]')?.click();
    text('.chat-chip').forEach((question) => seen.add(question));
    q('.chat-chip').click();
    await settle();
  }
  assert.ok(seen.size > 3, 'each new conversation offers its own questions');
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

test('when the admin has switched the chat off the question says so and the button goes when it is closed', async () => {
  installApi({ 'GET /chat/status': { available: true }, 'POST /chat': () => json({ detail: 'El chat no está disponible ahora mismo' }, 503) });
  await mountChat();
  q('.chat-fab').click();
  await ask('hola');
  assert.equal(q('.chat-error').textContent, 'El chat no está disponible ahora mismo');
  assert.ok(q('#chat-root'));
  q('[data-close]').click();
  assert.equal(q('#chat-root'), null);
});

// A phone's keyboard shrinks the visual viewport and the browser scrolls the page: the panel follows the visual viewport
function fakeViewport(height, offsetTop = 0) {
  const viewport = new window.EventTarget();
  Object.assign(viewport, { height, offsetTop });
  window.visualViewport = viewport;
  return viewport;
}
const root = () => document.getElementById('chat-root');

test('on a phone the open panel takes the position and the height of the visual viewport and follows the keyboard', async () => {
  const viewport = fakeViewport(800);
  installApi({ 'GET /chat/status': { available: true }, 'POST /chat': { answer: 'ok', in_scope: true } });
  await mountChat();
  assert.equal(root().style.getPropertyValue('--chat-height'), ''); // closed: nothing to follow
  q('.chat-fab').click();
  assert.equal(root().style.getPropertyValue('--chat-height'), '800px');
  assert.equal(root().style.getPropertyValue('--chat-top'), '0px');
  assert.ok(document.body.classList.contains('chat-open'));
  // the keyboard opens: the visual viewport is shorter and the browser has scrolled the page under it
  Object.assign(viewport, { height: 420, offsetTop: 133.4 });
  viewport.dispatchEvent(new window.Event('resize'));
  assert.equal(root().style.getPropertyValue('--chat-height'), '420px');
  assert.equal(root().style.getPropertyValue('--chat-top'), '133px');
  Object.assign(viewport, { offsetTop: 0 });
  viewport.dispatchEvent(new window.Event('scroll'));
  assert.equal(root().style.getPropertyValue('--chat-top'), '0px');
  // a re-render (an answer arrives) must not lose it: it lives on the container, which is not replaced
  await ask('hola');
  assert.equal(root().style.getPropertyValue('--chat-height'), '420px');
});

test('closing the panel stops following the viewport and lets the page scroll again', async () => {
  const viewport = fakeViewport(700);
  installApi({ 'GET /chat/status': { available: true } });
  await mountChat();
  q('.chat-fab').click();
  q('[data-close]').click();
  assert.equal(root().style.getPropertyValue('--chat-height'), '');
  assert.equal(document.body.classList.contains('chat-open'), false);
  viewport.height = 300;
  viewport.dispatchEvent(new window.Event('resize'));
  assert.equal(root().style.getPropertyValue('--chat-height'), '');
});

test('a browser without a visual viewport still opens and closes the chat', async () => {
  delete window.visualViewport;
  installApi({ 'GET /chat/status': { available: true } });
  await mountChat();
  q('.chat-fab').click();
  assert.equal(q('.chat-panel').hidden, false);
  assert.equal(root().style.getPropertyValue('--chat-height'), '');
  q('[data-close]').click();
  assert.equal(q('.chat-panel').hidden, true);
});

test('logging out while it is open leaves the page scrollable', async () => {
  fakeViewport(700);
  installApi({ 'GET /chat/status': { available: true } });
  await mountChat();
  q('.chat-fab').click();
  unmountChat();
  assert.equal(document.body.classList.contains('chat-open'), false);
});

test('the answer is drawn with its italics, bold, code and lists, and its markup stays text', async () => {
  installApi({
    'GET /chat/status': { available: true },
    'POST /chat': { answer: 'Tienes *Zelda* y **GTA** (`id`).\n1. Uno\n2. Dos\n- <b>x</b>\n# Título', in_scope: true },
  });
  await mountChat();
  q('.chat-fab').click();
  await ask('hola');
  const bot = q('.chat-bot');
  assert.equal(bot.querySelector('em').textContent, 'Zelda');
  assert.equal(bot.querySelector('p strong').textContent, 'GTA');
  assert.equal(bot.querySelector('code').textContent, 'id');
  assert.deepEqual(text('ol li', bot), ['Uno', 'Dos']);
  assert.deepEqual(text('ul li', bot), ['<b>x</b>']);
  assert.equal(bot.querySelector('b'), null);
  assert.equal(bot.querySelectorAll('p strong').length, 2); // the bold word and the heading
  assert.doesNotMatch(bot.textContent, /\*|`|#/);
});
