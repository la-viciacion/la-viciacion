import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
installDom('<a href="#" class="navbar-brand"><img alt=""></a>');
const { celebrateBirthday, knownBirthDate } = await import('../js/ui/birthday.js');

const ana = { username: 'ana', name: 'Ana' };
const bea = { username: 'bea', name: null };
const bob = { username: 'bob', name: 'Bob' };
const today = new Date(2026, 5, 15);
const reset = () => {
  document.querySelectorAll('.modal-overlay, .birthday-confetti').forEach((el) => el.remove());
  document.querySelector('.navbar-brand').classList.remove('skin-birthday');
};

test('on their birthday the logo wears the cake and a modal greets them, without their age', async () => {
  installApi({ 'GET /users/ana/settings': { birth_date: '1990-06-15' } });
  await celebrateBirthday(ana, today);
  assert.ok(document.querySelector('.navbar-brand').classList.contains('skin-birthday'));
  const modal = document.querySelector('.birthday-modal');
  assert.match(modal.textContent, /Feliz cumpleaños, Ana/);
  assert.doesNotMatch(modal.textContent, /\d/);
  assert.ok(document.querySelector('.birthday-confetti'));
  assert.equal(knownBirthDate(ana), '1990-06-15');
  modal.querySelector('[data-close]').click();
  assert.equal(document.querySelector('.birthday-modal'), null);
  assert.equal(document.querySelector('.birthday-confetti'), null);
});

test('the second time that day it keeps the cake but does not greet again', async () => {
  reset();
  installApi({});
  await celebrateBirthday(ana, today);
  assert.ok(document.querySelector('.navbar-brand').classList.contains('skin-birthday'));
  assert.equal(document.querySelector('.birthday-modal'), null);
});

test('the name falls back to the username', async () => {
  reset();
  installApi({ 'GET /users/bea/settings': { birth_date: '1990-06-15' } });
  await celebrateBirthday(bea, today);
  assert.match(document.querySelector('.birthday-modal').textContent, /Feliz cumpleaños, bea/);
});

test('any other day, or with no birth date, nothing happens', async () => {
  reset();
  installApi({ 'GET /users/bob/settings': { birth_date: '1990-06-16' } });
  await celebrateBirthday(bob, today);
  assert.equal(document.querySelector('.birthday-modal'), null);
  assert.equal(document.querySelector('.navbar-brand').classList.contains('skin-birthday'), false);
  installApi({ 'GET /users/cy/settings': { birth_date: null } });
  await celebrateBirthday({ username: 'cy', name: 'Cy' }, today);
  await settle();
  assert.equal(document.querySelector('.birthday-modal'), null);
});
