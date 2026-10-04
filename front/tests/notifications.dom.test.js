import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
installDom('<div id="el"></div>');
const { initNotifications, noticeOn } = await import('../js/pages/profile/notifications.js');

const DEFAULTS = { forgotten_timer_telegram: true, forgotten_timer_push: true, forgotten_timer_hours: 4 };
const settings = (own = {}) => ({ forgotten_timer_hours: null, forgotten_timer_telegram: null, forgotten_timer_push: null, ...own, defaults: DEFAULTS });

const show = async (own) => {
  const calls = installApi({ 'GET /users/ana/settings': settings(own), 'PATCH /users/ana/settings': settings() });
  const el = document.querySelector('#el');
  await initNotifications(el, { path: '/users/ana/settings' });
  return { calls, form: el.querySelector('#pfForgotten') };
};
const fire = async (target, type) => {
  target.dispatchEvent(new window.Event(type, { bubbles: true, cancelable: true }));
  await settle();
};

test('a notice is on unless every channel is off, an unset channel counting as the default', () => {
  assert.equal(noticeOn(settings(), 'forgotten_timer'), true);
  assert.equal(noticeOn(settings({ forgotten_timer_telegram: false }), 'forgotten_timer'), true);
  assert.equal(noticeOn(settings({ forgotten_timer_telegram: false, forgotten_timer_push: false }), 'forgotten_timer'), false);
});

test('by default it is on, with both channels and the options visible', async () => {
  const { form } = await show();
  assert.equal(form.elements.enabled.checked, true);
  assert.equal(form.elements.telegram.checked && form.elements.push.checked, true);
  assert.equal(form.querySelector('.pf-options').hidden, false);
  assert.equal(form.elements.hours.placeholder, '4');
});

test('with both channels off it shows as off and hides the options', async () => {
  const { form } = await show({ forgotten_timer_telegram: false, forgotten_timer_push: false });
  assert.equal(form.elements.enabled.checked, false);
  assert.equal(form.querySelector('.pf-options').hidden, true);
});

test('switching it off saves both channels as off', async () => {
  const { calls, form } = await show();
  form.elements.enabled.checked = false;
  await fire(form.elements.enabled, 'change');
  assert.deepEqual(calls.at(-1).body, { forgotten_timer_telegram: false, forgotten_timer_push: false });
  assert.equal(form.querySelector('.pf-options').hidden, true);
});

test('switching it on again turns both channels on when none was left', async () => {
  const { calls, form } = await show({ forgotten_timer_telegram: false, forgotten_timer_push: false });
  form.elements.enabled.checked = true;
  await fire(form.elements.enabled, 'change');
  assert.deepEqual(calls.at(-1).body, { forgotten_timer_telegram: true, forgotten_timer_push: true });
  assert.equal(form.querySelector('.pf-options').hidden, false);
});

test('saving sends the channels and the hours; an empty field goes back to the default', async () => {
  const { calls, form } = await show();
  form.elements.push.checked = false;
  form.elements.hours.value = '6';
  await fire(form, 'submit');
  assert.deepEqual(calls.at(-1).body, { forgotten_timer_telegram: true, forgotten_timer_push: false, forgotten_timer_hours: 6 });
  form.elements.hours.value = '';
  await fire(form, 'submit');
  assert.equal(calls.at(-1).body.forgotten_timer_hours, null);
});

test('it refuses to save without a channel or with bad hours, without asking the API', async () => {
  const { calls, form } = await show();
  const before = calls.length;
  form.elements.telegram.checked = form.elements.push.checked = false;
  await fire(form, 'submit');
  assert.match(form.querySelector('.pf-msg').textContent, /al menos un canal/);
  form.elements.telegram.checked = true;
  form.elements.hours.value = '25';
  await fire(form, 'submit');
  assert.match(form.querySelector('.pf-msg').textContent, /entre 1 y 24/);
  assert.equal(calls.length, before);
});
