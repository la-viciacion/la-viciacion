import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
installDom('<div id="el"></div>');
const { initNotifications } = await import('../js/pages/profile/notifications.js');

const DEFAULTS = {
  forgotten_timer_telegram: true, forgotten_timer_push: true, wishlist_release_telegram: true, wishlist_release_push: true, forgotten_timer_hours: 4,
  challenge_notices_telegram: true, challenge_notices_push: true, challenge_reminders_telegram: false, challenge_reminders_push: false,
};
const settings = (own = {}) => ({ forgotten_timer_hours: null, forgotten_timer_telegram: null, forgotten_timer_push: null, wishlist_release_telegram: null, wishlist_release_push: null, ...own, defaults: DEFAULTS });

const show = async (own, patch = () => settings()) => {
  const calls = installApi({ 'GET /users/ana/settings': settings(own), 'PATCH /users/ana/settings': patch });
  const el = document.querySelector('#el');
  await initNotifications(el, { path: '/users/ana/settings' });
  const box = (name) => el.querySelector(`input[name="forgotten_timer_${name}"]`);
  return { calls, el, telegram: box('telegram'), push: box('push'), options: el.querySelector('[data-options]') };
};
const toggle = async (box) => {
  box.checked = !box.checked;
  box.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
};
const submit = async (options, value) => {
  options.elements.hours.value = value;
  options.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
};

test('it lists the notices as a row with a checkbox per channel, both on by default, and the hours open', async () => {
  const { el, telegram, push, options } = await show();
  assert.equal(el.querySelector('.pf-notice-name').firstChild.textContent, 'Timer olvidado');
  assert.deepEqual([telegram.checked, push.checked], [true, true]);
  assert.equal(options.hidden, false);
  assert.equal(options.elements.hours.placeholder, '4');
});

test('it shows the channels the user chose, and keeps the hours closed when none is checked', async () => {
  const one = await show({ forgotten_timer_telegram: false });
  assert.deepEqual([one.telegram.checked, one.push.checked], [false, true]);
  assert.equal(one.options.hidden, false);
  const none = await show({ forgotten_timer_telegram: false, forgotten_timer_push: false });
  assert.equal(none.options.hidden, true);
});

test('a checkbox saves right away with both channels, and the hours open or close with them', async () => {
  const { calls, telegram, push, options } = await show();
  await toggle(telegram);
  assert.deepEqual(calls.at(-1).body, { forgotten_timer_telegram: false, forgotten_timer_push: true });
  assert.equal(options.hidden, false);
  await toggle(push);
  assert.deepEqual(calls.at(-1).body, { forgotten_timer_telegram: false, forgotten_timer_push: false });
  assert.equal(options.hidden, true);
  await toggle(telegram);
  assert.equal(options.hidden, false);
});

test('a checkbox goes back if the API refuses the change', async () => {
  const refuse = () => new Response(JSON.stringify({ detail: 'No se pudo guardar' }), { status: 400, headers: { 'Content-Type': 'application/json' } });
  const { telegram, options, el } = await show({}, refuse);
  await toggle(telegram);
  assert.equal(telegram.checked, true);
  assert.equal(options.hidden, false);
  assert.match(el.querySelector('.pf-msg').textContent, /No se pudo guardar/);
});

test('saving the hours sends only the hours; an empty field goes back to the default', async () => {
  const { calls, options } = await show();
  await submit(options, '6');
  assert.deepEqual(calls.at(-1).body, { forgotten_timer_hours: 6 });
  await submit(options, '');
  assert.deepEqual(calls.at(-1).body, { forgotten_timer_hours: null });
});

test('bad hours are refused without asking the API', async () => {
  const { calls, options, el } = await show();
  const before = calls.length;
  await submit(options, '25');
  assert.match(el.querySelector('.pf-msg').textContent, /entre 1 y 24/);
  assert.equal(calls.length, before);
});

test('the wishlist notice is another row with its two channels, on by default, and has no options', async () => {
  const { calls, el } = await show();
  const row = el.querySelector('[data-notice="wishlist_release"]');
  assert.equal(row.querySelector('.pf-notice-name').firstChild.textContent, 'Sale un juego deseado');
  const [telegram, push] = row.querySelectorAll('input');
  assert.deepEqual([telegram.checked, push.checked], [true, true]);
  assert.equal(el.querySelector('[data-options="wishlist_release"]'), null);
  await toggle(push);
  assert.deepEqual(calls.at(-1).body, { wishlist_release_telegram: true, wishlist_release_push: false });
});

test('the wishlist notice shows the channels the user chose', async () => {
  const { el } = await show({ wishlist_release_telegram: false });
  const [telegram, push] = el.querySelectorAll('[data-notice="wishlist_release"] input');
  assert.deepEqual([telegram.checked, push.checked], [false, true]);
});

test('the hours are folded, and the one Guardar button at the end of the card is always there', async () => {
  const { el, telegram, push, options } = await show();
  const save = el.querySelector('[data-save="forgotten_timer"]');
  assert.equal(save.querySelector('button').getAttribute('form'), options.id);
  assert.equal(el.querySelectorAll('button[type="submit"]').length, 1);
  assert.equal(el.querySelector('.pf-notices').lastElementChild.previousElementSibling.previousElementSibling, save);
  assert.equal(options.querySelector('details').open, false);
  assert.equal(save.hidden, false);
  await toggle(telegram);
  await toggle(push);
  assert.equal(save.hidden, false);
});

test('saving without changes sends the same hours and says it is saved', async () => {
  const { calls, el, options } = await show({ forgotten_timer_hours: 6 });
  options.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(calls.at(-1).body, { forgotten_timer_hours: 6 });
  assert.match(el.querySelector('.pf-msg').textContent, /Guardado/);
});

test('the challenge notices are on by default and the reminders are off until the player turns them on', async () => {
  const { el, calls } = await show();
  const box = (notice, channel) => el.querySelector(`input[name="${notice}_${channel}"]`);
  assert.deepEqual([box('challenge_notices', 'telegram').checked, box('challenge_notices', 'push').checked], [true, true]);
  assert.deepEqual([box('challenge_reminders', 'telegram').checked, box('challenge_reminders', 'push').checked], [false, false]);
  await toggle(box('challenge_reminders', 'push'));
  assert.deepEqual(calls.at(-1).body, { challenge_reminders_telegram: false, challenge_reminders_push: true });
});

test('what the player chose for the challenge notices is what is shown', async () => {
  const { el } = await show({ challenge_notices_telegram: false, challenge_reminders_telegram: true });
  const box = (notice, channel) => el.querySelector(`input[name="${notice}_${channel}"]`);
  assert.deepEqual([box('challenge_notices', 'telegram').checked, box('challenge_notices', 'push').checked], [false, true]);
  assert.equal(box('challenge_reminders', 'telegram').checked, true);
});
