import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
installDom('<div id="el"></div>');
const { initNotifications } = await import('../js/pages/profile/notifications.js');

const DEFAULTS = { forgotten_timer_telegram: true, forgotten_timer_push: true, forgotten_timer_hours: 4 };
const settings = (own = {}) => ({ forgotten_timer_hours: null, forgotten_timer_telegram: null, forgotten_timer_push: null, ...own, defaults: DEFAULTS });

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
