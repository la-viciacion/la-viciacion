import assert from 'node:assert/strict';
import { test } from 'node:test';
import { activeItem, bottomTabs, menuFoot, menuPages, menuSections, sectionOf } from '../js/lib/menu.js';

const ids = () => menuSections().flatMap((s) => s.items.map((i) => i.id));

test('the sections group the pages by what they are about', () => {
  assert.deepEqual(menuSections().map((s) => s.label), ['Principal', 'Grupo', 'Juegos', 'Tú']);
  const section = (label) => menuSections().find((s) => s.label === label).items.map((i) => i.id);
  assert.deepEqual(section('Principal'), ['home', 'activity']);
  assert.deepEqual(section('Grupo'), ['season', 'players', 'challenges', 'achievements']);
  assert.deepEqual(section('Juegos'), ['games', 'library', 'calendar']);
  assert.deepEqual(section('Tú'), ['profile', 'wishlist', 'recommendations']);
});

test('the statistics have no entry until they are ready (their page still opens by its address)', () => {
  assert.ok(![...ids(), ...menuFoot({ is_admin: true }).map((i) => i.id)].includes('stats'));
  assert.equal(activeItem('#/stats'), null);
});

test('the last section has the settings and the server for everybody and the administration only for an admin', () => {
  assert.deepEqual(menuFoot({ is_admin: false }).map((i) => i.id), ['settings', 'server']);
  assert.deepEqual(menuFoot({ is_admin: true }).map((i) => i.id), ['settings', 'server', 'admin']);
});

test('every id and address is unique', () => {
  const items = menuPages({ is_admin: true });
  assert.equal(new Set(items.map((i) => i.id)).size, items.length);
  assert.equal(new Set(items.map((i) => i.href)).size, items.length);
});

test('the bottom tabs lead to the main page of a section and every item belongs to one', () => {
  assert.deepEqual(bottomTabs().map((t) => t.label), ['Inicio', 'Grupo', 'Juegos', 'Tú']);
  for (const [item, tab] of [['home', 'principal'], ['activity', 'principal'], ['challenges', 'group'], ['players', 'group'], ['library', 'games'], ['wishlist', 'you'], ['settings', 'you']]) {
    assert.equal(sectionOf(item), tab);
  }
  assert.equal(sectionOf('server'), null);
  assert.equal(sectionOf('admin'), null);
  assert.equal(sectionOf(null), null);
  for (const tab of bottomTabs()) assert.equal(sectionOf(activeItem(tab.href)), tab.id, tab.label);
});

test('an address highlights its item, the most specific one first', () => {
  assert.equal(activeItem(''), 'home');
  assert.equal(activeItem('#'), 'home');
  assert.equal(activeItem('#/activity'), 'activity');
  assert.equal(activeItem('#/recap'), null);
  assert.equal(activeItem('#/story/2026-09'), null);
  assert.equal(activeItem('#/profile'), 'profile');
  assert.equal(activeItem('#/profile/resumen'), 'profile');
  assert.equal(activeItem('#/recommendations'), 'recommendations');
  assert.equal(activeItem('#/profile/ajustes'), 'settings');
  assert.equal(activeItem('#/admin/users'), 'admin');
  assert.equal(activeItem('#/games'), 'games');
  assert.equal(activeItem('#/library'), 'library');
  assert.equal(activeItem('#/wishlist'), 'wishlist');
  assert.equal(activeItem('#/calendar'), 'calendar');
  assert.equal(activeItem('#/challenges'), 'challenges');
  assert.equal(activeItem('#/achievements'), 'achievements');
  assert.equal(activeItem('#/players'), 'players');
  assert.equal(activeItem('#/server'), 'server');
  assert.equal(activeItem('#/player/3'), 'players'); // a player's page belongs to the players
  assert.equal(activeItem('#/game/celeste'), 'games'); // a game's page belongs to the games
});

test('a page without an item highlights nothing', () => {
  assert.equal(activeItem('#/profilex'), null);
});
