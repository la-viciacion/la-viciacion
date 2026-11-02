import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>', 'http://localhost/');
globalThis.location = window.location;
globalThis.URL.createObjectURL = () => 'blob:photo';
const { inviteToProfile, profileCard } = await import('../js/ui/profile-invite.js');
const { forgetAvatars } = await import('../js/lib/api.js');
const { html, mount } = await import('../js/lib/html.js');

const NOW = new Date(2026, 10, 2);
const bar = () => document.querySelector('.profile-invite');
const settings = (extra = {}) => ({ 'GET /users/ana/settings': { place_name: null, birth_date: null, ...extra } });
// the photo: a 404 means there is none
const noPhoto = { 'GET /users/ana/avatar': () => new Response('', { status: 404 }) };

function reset() {
  forgetAvatars(); // the photo is remembered per player
  document.querySelectorAll('.profile-invite, .push-invite, .recap-invite').forEach((el) => el.remove());
  localStorage.removeItem('lv-profile-invite-ana');
  window.location.hash = '#/';
}

test('a profile with things missing gets a bar with the percentage, and "Ahora no" waits a week', async () => {
  reset();
  installApi({ ...noPhoto, ...settings() });
  await inviteToProfile({ username: 'ana' }, NOW);
  assert.match(bar().textContent, /Tu perfil está al 0 %/);
  assert.match(bar().textContent, /Te faltan la foto, la ciudad y la fecha de nacimiento/);
  assert.equal(bar().querySelector('a').getAttribute('href'), '#/profile/resumen');
  bar().querySelector('[data-act="later"]').click();
  assert.equal(bar(), null);

  const calls = installApi({});
  await inviteToProfile({ username: 'ana' }, new Date(2026, 10, 5));
  assert.equal(bar(), null);
  assert.equal(calls.length, 0, 'while it waits nothing is even asked');
  installApi({ ...noPhoto, ...settings() });
  await inviteToProfile({ username: 'ana' }, new Date(2026, 10, 9));
  assert.notEqual(bar(), null);
});

test('a complete profile is not bothered and is not asked about again', async () => {
  reset();
  installApi({ 'GET /users/ana/avatar': () => new Response('x', { status: 200, headers: { 'Content-Type': 'image/jpeg' } }), ...settings({ place_name: 'Valencia', birth_date: '1990-05-01' }) });
  await inviteToProfile({ username: 'ana' }, NOW);
  assert.equal(bar(), null);
  const calls = installApi({});
  await inviteToProfile({ username: 'ana' }, NOW);
  assert.equal(calls.length, 0);
});

test('it never lands on another bar or on the profile', async () => {
  reset();
  const calls = installApi({});
  document.body.insertAdjacentHTML('beforeend', '<div class="push-invite"></div>');
  await inviteToProfile({ username: 'ana' }, NOW);
  document.querySelector('.push-invite').remove();
  window.location.hash = '#/profile/resumen';
  await inviteToProfile({ username: 'ana' }, NOW);
  assert.equal(bar(), null);
  assert.equal(calls.length, 0);
});

test('the card of the profile shows the percentage and only offers Completar for what Ajustes fills', () => {
  mount(document.getElementById('main'), html`${profileCard(['photo', 'place'])}`);
  const card = document.querySelector('.profile-card');
  assert.match(card.textContent, /al 33 %/);
  assert.equal(card.querySelector('[role="progressbar"]').getAttribute('aria-valuenow'), '33');
  assert.ok(card.querySelector('[data-go="ajustes"]'));
  mount(document.getElementById('main'), html`${profileCard(['photo'])}`);
  assert.equal(document.querySelector('[data-go]'), null);
  mount(document.getElementById('main'), html`${profileCard([])}`);
  assert.equal(document.querySelector('.profile-card'), null);
});

// last: following the link silences the bar for the rest of this page load, which the other tests would feel
test('"Completar" takes the player on without spending a reminder, and the bar does not come back in that visit', async () => {
  reset();
  installApi({ ...noPhoto, ...settings() });
  await inviteToProfile({ username: 'ana' }, NOW);
  bar().querySelector('[data-act="fill"]').click();
  assert.equal(bar(), null);
  assert.equal(JSON.parse(localStorage.getItem('lv-profile-invite-ana')).until, 0, 'no wait started');
  await inviteToProfile({ username: 'ana' }, NOW);
  assert.equal(bar(), null, 'not on the next page either');
});
