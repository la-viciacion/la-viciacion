import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
const window = installDom('<div id="pfChat"></div>', 'http://localhost/');
globalThis.location = window.location;
const { initChatBubble } = await import('../js/pages/profile/chat-bubble.js');
const { unmountChat } = await import('../js/ui/chat.js');

const el = () => document.querySelector('#pfChat');
const box = () => el().querySelector('input[name="show"]');
const toggle = async (checked) => { box().checked = checked; box().dispatchEvent(new window.Event('change', { bubbles: true })); await settle(); };

test('with the chat off for the group there is nothing to switch', async () => {
  installApi({ 'GET /chat/status': { available: false, bubble: true } });
  await initChatBubble(el(), { path: '/users/ana/settings' });
  assert.equal(box(), null);
});

test('hiding and showing the button is saved and takes effect at once', async () => {
  const calls = installApi({
    'GET /chat/status': { available: true, bubble: true },
    'PATCH /users/ana/settings': { show_chat: false },
  });
  await initChatBubble(el(), { path: '/users/ana/settings' });
  await settle();
  assert.equal(box().checked, true);
  await toggle(false);
  assert.deepEqual(calls.find((c) => c.method === 'PATCH').body, { show_chat: false });
  assert.equal(document.querySelector('#chat-root'), null);
  await toggle(true);
  assert.equal(calls.filter((c) => c.method === 'PATCH')[1].body.show_chat, true);
  assert.ok(document.querySelector('#chat-root'));
  unmountChat();
});

test('a hidden button shows as off, and a failed save undoes the switch', async () => {
  installApi({
    'GET /chat/status': { available: true, bubble: false },
    'PATCH /users/ana/settings': () => json({ detail: 'No se ha podido guardar' }, 500),
  });
  await initChatBubble(el(), { path: '/users/ana/settings' });
  assert.equal(box().checked, false);
  await toggle(true);
  assert.equal(box().checked, false);
  assert.equal(el().querySelector('.pf-msg').textContent, 'No se ha podido guardar');
});
