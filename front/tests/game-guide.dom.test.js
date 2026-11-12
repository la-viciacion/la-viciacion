import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json } from './dom.js';

installStorage();
installDom('<div id="slot"></div>');
const { showGuide } = await import('../js/ui/game-guide.js');
const { forgetConversations, forgetGuideStatus, guideAvailable } = await import('../js/lib/guide.js');

const GAME = { id: 'hades', name: 'Hades' };
const slot = () => document.getElementById('slot');

beforeEach(() => {
  forgetConversations();
  slot().replaceChildren();
});

test('a player whose key must pay and has none is shown how to add it, instead of a box that would fail', async () => {
  installApi({ 'GET /guide/status': { available: true, needs_key: true, paid_by: null } });
  await showGuide(slot(), GAME);
  assert.equal(slot().querySelector('.chat-input'), null);
  const link = slot().querySelector('a.pf-btn');
  assert.equal(link.getAttribute('href'), '#/profile/ajustes/ia');
  assert.match(slot().textContent, /tiene un coste mayor, así que funciona con tu propia clave de OpenAI/);
});

test('whoever can ask sees the guide as before', async () => {
  installApi({ 'GET /guide/status': { available: true, needs_key: false, paid_by: 'user' } });
  await showGuide(slot(), GAME);
  assert.ok(slot().querySelector('[data-open]'));
  assert.equal(slot().querySelector('a.pf-btn'), null);
});

test('a guide that is off shows nothing', async () => {
  installApi({ 'GET /guide/status': { available: false, needs_key: false, paid_by: null } });
  await showGuide(slot(), GAME);
  assert.equal(slot().textContent.trim(), '');
});

test('the quick access of the timer is offered only when the player can ask right now', async () => {
  installApi({ 'GET /guide/status': { available: true, needs_key: true } });
  assert.equal(await guideAvailable(), false);
  forgetGuideStatus();
  installApi({ 'GET /guide/status': { available: true, needs_key: false } });
  assert.equal(await guideAvailable(), true);
});

test('a failure is "off" and is not remembered, and what is known is asked once per visit', async () => {
  installApi({ 'GET /guide/status': () => json({ detail: 'down' }, 500) });
  assert.equal(await guideAvailable(), false);
  const calls = installApi({ 'GET /guide/status': { available: true, needs_key: false } });
  assert.equal(await guideAvailable(), true);
  assert.equal(await guideAvailable(), true);
  assert.equal(calls.length, 1);
});
