import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
installDom('<div id="el"></div>');
const { initAbout } = await import('../js/pages/profile/about.js');

const MADRID = { name: 'Madrid, Comunidad de Madrid, España', latitude: 40.4165, longitude: -3.70256 };
const settings = (own = {}) => ({ place_name: null, place_latitude: null, place_longitude: null, birth_date: null, ...own });

const show = async (own, extra = {}) => {
  const calls = installApi({
    'GET /users/ana/settings': settings(own),
    'GET /users/places/search': [MADRID],
    'PATCH /users/ana/settings': ({ body }) => settings({ ...own, ...body }),
    ...extra,
  });
  const el = document.querySelector('#el');
  const about = await initAbout(el, { path: '/users/ana/settings' });
  return { calls, el, about, current: el.querySelector('[data-current]'), remove: el.querySelector('[data-remove]'), birth: el.querySelector('[name="birth_date"]'), help: el.querySelector('[data-help]') };
};

const search = async (el, query) => {
  el.querySelector('[name="place_query"]').value = query;
  el.querySelector('[data-search]').click();
  await settle();
};

test('without a city it says so and offers no way to remove one', async () => {
  const { current, remove } = await show();
  assert.equal(current.textContent, 'Sin ciudad');
  assert.equal(remove.hidden, true);
});

test('nothing it shows says what the city and the birth date are for', async () => {
  const { el } = await show();
  assert.doesNotMatch(el.textContent, /logro|tiempo|clima|cumplea/i);
});

test('searching lists the cities and picking one only stages it: nothing is saved until the form is', async () => {
  const { calls, el, about, current, remove } = await show();
  await search(el, 'Madrid');
  assert.deepEqual(calls.at(-1), { method: 'GET', path: '/users/places/search?q=Madrid', body: undefined });
  const pick = el.querySelector('[data-pick="0"]');
  assert.equal(pick.textContent.trim(), MADRID.name);
  pick.click();
  assert.equal(current.textContent, MADRID.name);
  assert.equal(remove.hidden, false);
  assert.equal(el.querySelectorAll('[data-pick]').length, 0);
  assert.equal(calls.filter((call) => call.method === 'PATCH').length, 0);
  await about.save();
  assert.deepEqual(calls.at(-1).body, { place_name: MADRID.name, place_latitude: MADRID.latitude, place_longitude: MADRID.longitude });
});

test('Enter in the search box searches instead of submitting the form', async () => {
  const { calls, el } = await show();
  const input = el.querySelector('[name="place_query"]');
  input.value = 'Madrid';
  const enter = new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
  input.dispatchEvent(enter);
  await settle();
  assert.equal(enter.defaultPrevented, true);
  assert.equal(calls.at(-1).path, '/users/places/search?q=Madrid');
});

test('a search that is too short asks for more letters without calling the API', async () => {
  const { calls, el, help } = await show();
  const before = calls.length;
  await search(el, 'M');
  assert.equal(calls.length, before);
  assert.match(help.textContent, /al menos dos letras/);
});

test('removing the city clears the three values together when saved', async () => {
  const { calls, about, remove, current } = await show({ place_name: MADRID.name, place_latitude: 40.4, place_longitude: -3.7 });
  assert.equal(current.textContent, MADRID.name);
  remove.click();
  assert.equal(current.textContent, 'Sin ciudad');
  await about.save();
  assert.deepEqual(calls.at(-1).body, { place_name: null, place_latitude: null, place_longitude: null });
});

test('saving without changes sends nothing, and only what changed is sent', async () => {
  const { calls, about, birth } = await show({ birth_date: '1990-02-28' });
  assert.equal(birth.value, '1990-02-28');
  await about.save();
  assert.equal(calls.filter((call) => call.method === 'PATCH').length, 0);
  birth.value = '1991-03-04';
  await about.save();
  assert.deepEqual(calls.at(-1).body, { birth_date: '1991-03-04' });
  birth.value = '';
  await about.save();
  assert.deepEqual(calls.at(-1).body, { birth_date: null });
});

test('an error of the search is shown, not swallowed', async () => {
  const { el, help } = await show({}, { 'GET /users/places/search': () => new Response(JSON.stringify({ detail: 'No se pueden buscar ciudades ahora mismo, inténtalo más tarde' }), { status: 503, headers: { 'Content-Type': 'application/json' } }) });
  await search(el, 'Madrid');
  assert.match(help.textContent, /No se pueden buscar ciudades/);
});
