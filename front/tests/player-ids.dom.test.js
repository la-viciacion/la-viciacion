import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installDom, installStorage } from './dom.js';

installStorage();
installDom('<div id="el"></div>');
const { gameIdsView } = await import('../js/pages/player/index.js');
const { mount } = await import('../js/lib/html.js');

const show = (ids) => {
  const el = document.querySelector('#el');
  mount(el, gameIdsView(ids));
  return el;
};

test('the player page lists only the ids the player filled in, labelled by service', () => {
  const el = show({ steam_id: 'ana_steam', discord_id: 'ana#1' });
  assert.deepEqual([...el.querySelectorAll('.pl-id-service')].map((n) => n.textContent), ['Steam', 'Discord']);
  assert.deepEqual([...el.querySelectorAll('.pl-id-value')].map((n) => n.textContent), ['ana_steam', 'ana#1']);
  assert.deepEqual([...el.querySelectorAll('[data-copy]')].map((n) => n.dataset.copy), ['ana_steam', 'ana#1']);
});

test('without any id there is nothing to show', () => {
  assert.equal(gameIdsView({}), '');
  assert.equal(gameIdsView(undefined), '');
});

test('an id is text, never markup', () => {
  const el = show({ xbox_id: '<img src=x onerror=alert(1)>' });
  assert.equal(el.querySelector('img'), null);
  assert.match(el.querySelector('.pl-id-value').textContent, /<img/);
});

test('every service has its own logo, and the pill still names it for who cannot see the logo', async () => {
  const { GAME_IDS } = await import('../js/lib/game-ids.js');
  const el = show(Object.fromEntries(GAME_IDS.map(([column]) => [column, 'x'])));
  const pills = [...el.querySelectorAll('.pl-id')];
  assert.equal(pills.length, GAME_IDS.length);
  assert.equal(new Set(pills.map((pill) => pill.querySelector('svg path').getAttribute('d'))).size, GAME_IDS.length);
  assert.deepEqual(pills.map((pill) => pill.querySelector('.pl-id-service').textContent), GAME_IDS.map(([, label]) => label));
});
