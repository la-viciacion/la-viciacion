import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { installDom } from './dom.js';

const window = installDom('<a href="#" class="navbar-brand"><img alt=""></a><input id="field">');
const { LOGO_MESSAGES, mountEasterEggs } = await import('../js/ui/easter-eggs.js');
const reported = [];
const armed = { logo: true, konami: true };
mountEasterEggs({ attempt: async (egg) => { reported.push(egg); return armed[egg]; } });
mountEasterEggs(); // mounting twice must not double the listeners

afterEach(() => document.querySelectorAll('.toast, .konami-rain, .logo-blast').forEach((el) => el.remove()));

// an egg reports the attempt and asks whether it is armed before it goes off: let that answer arrive
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const press = (key, target = document) => target.dispatchEvent(new window.KeyboardEvent('keydown', { key, bubbles: true }));
const toasts = () => [...document.querySelectorAll('.toast')].map((el) => el.textContent);
const KONAMI = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];
const clickLogo = (times) => { for (let i = 0; i < times; i++) document.querySelector('.navbar-brand').click(); };

const finger = (type, x, y) => {
  const event = new window.Event(type, { bubbles: true });
  const touch = { clientX: x, clientY: y };
  event.touches = type === 'touchend' ? [] : [touch];
  event.changedTouches = [touch];
  document.dispatchEvent(event);
};
const swipe = (dx, dy) => { finger('touchstart', 100, 100); finger('touchend', 100 + dx, 100 + dy); };

test('the Konami code on a keyboard rains games and says so once', async () => {
  for (const key of KONAMI) press(key);
  await settle();
  assert.equal(document.querySelectorAll('.konami-rain span').length, 36);
  assert.deepEqual(toasts(), ['↑↑↓↓←→←→BA · +30 vidas']);
  assert.deepEqual(reported, ['konami']);
});

test('on a phone the same code is swiped and tapped', async () => {
  for (const [dx, dy] of [[0, -90], [0, -90], [0, 90], [0, 90], [-90, 0], [90, 0], [-90, 0], [90, 0], [0, 0], [0, 0]]) swipe(dx, dy);
  await settle();
  assert.equal(document.querySelectorAll('.konami-rain').length, 1);
  assert.equal(toasts().length, 1);
});

test('typing in a field never triggers it', async () => {
  const field = document.getElementById('field');
  for (const key of KONAMI) press(key, field);
  await settle();
  assert.equal(document.querySelector('.konami-rain'), null);
});

test('seven clicks on the logo show one of the messages', async () => {
  clickLogo(6);
  await settle();
  assert.deepEqual(toasts(), []);
  clickLogo(1);
  await settle();
  assert.equal(toasts().length, 1);
  assert.ok(LOGO_MESSAGES.includes(toasts()[0]));
});

test('the seventh click also blows the logo up, once, and the blast clears itself', async () => {
  clickLogo(7);
  await settle();
  assert.equal(document.querySelectorAll('.logo-blast').length, 1);
  assert.equal(document.querySelectorAll('.logo-blast-spark').length, 28);
  assert.ok(document.querySelector('.navbar-brand').classList.contains('logo-shake'));
  assert.deepEqual(reported.filter((egg) => egg === 'logo'), ['logo', 'logo']); // attempted each time, also by the click test above
});

test('an egg whose achievement cannot be earned yet does not go off, so nobody finds it too early', async () => {
  const before = reported.length;
  armed.logo = false;
  armed.konami = false;
  clickLogo(7);
  for (const key of KONAMI) press(key);
  await settle();
  assert.equal(document.querySelector('.logo-blast'), null);
  assert.equal(document.querySelector('.konami-rain'), null);
  assert.deepEqual(toasts(), []);
  assert.deepEqual(reported.slice(before), ['logo', 'konami']); // the attempt is still reported, so the API can log it
});

test('an egg goes off for the one that is armed and not for the other', async () => {
  armed.logo = false;
  armed.konami = true;
  clickLogo(7);
  for (const key of KONAMI) press(key);
  await settle();
  assert.equal(document.querySelector('.logo-blast'), null);
  assert.equal(document.querySelectorAll('.konami-rain').length, 1);
});
