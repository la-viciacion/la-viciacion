import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installDom } from './dom.js';

const window = installDom('<a href="#" class="navbar-brand"><img alt=""></a><input id="field">');
const { LOGO_MESSAGES, mountEasterEggs } = await import('../js/ui/easter-eggs.js');
mountEasterEggs();
mountEasterEggs(); // mounting twice must not double the listeners

afterEach(() => document.querySelectorAll('.toast, .konami-rain').forEach((el) => el.remove()));

const press = (key, target = document) => target.dispatchEvent(new window.KeyboardEvent('keydown', { key, bubbles: true }));
const toasts = () => [...document.querySelectorAll('.toast')].map((el) => el.textContent);

const finger = (type, x, y) => {
  const event = new window.Event(type, { bubbles: true });
  const touch = { clientX: x, clientY: y };
  event.touches = type === 'touchend' ? [] : [touch];
  event.changedTouches = [touch];
  document.dispatchEvent(event);
};
const swipe = (dx, dy) => { finger('touchstart', 100, 100); finger('touchend', 100 + dx, 100 + dy); };

test('the Konami code on a keyboard rains games and says so once', () => {
  for (const key of ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a']) press(key);
  assert.equal(document.querySelectorAll('.konami-rain span').length, 36);
  assert.deepEqual(toasts(), ['↑↑↓↓←→←→BA · +30 vidas']);
});

test('on a phone the same code is swiped and tapped', () => {
  for (const [dx, dy] of [[0, -90], [0, -90], [0, 90], [0, 90], [-90, 0], [90, 0], [-90, 0], [90, 0], [0, 0], [0, 0]]) swipe(dx, dy);
  assert.equal(document.querySelectorAll('.konami-rain').length, 1);
  assert.equal(toasts().length, 1);
});

test('typing in a field never triggers it', () => {
  const field = document.getElementById('field');
  for (const key of ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a']) press(key, field);
  assert.equal(document.querySelector('.konami-rain'), null);
});

test('seven clicks on the logo show one of the messages', () => {
  const logo = document.querySelector('.navbar-brand');
  for (let i = 0; i < 6; i++) logo.click();
  assert.deepEqual(toasts(), []);
  logo.click();
  assert.equal(toasts().length, 1);
  assert.ok(LOGO_MESSAGES.includes(toasts()[0]));
});
