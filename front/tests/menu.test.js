import assert from 'node:assert/strict';
import { test } from 'node:test';
import { activeItem, menuSections } from '../js/lib/menu.js';

const ids = (user) => menuSections(user).flatMap((s) => s.items.map((i) => i.id));

test('a player sees every section but the administration', () => {
  assert.deepEqual(ids({ is_admin: false }), ['home', 'activity', 'games', 'library', 'players', 'calendar', 'achievements', 'stats', 'server', 'profile', 'wishlist', 'recommendations', 'challenges', 'settings']);
  assert.deepEqual(menuSections({ is_admin: false }).map((s) => s.label), ['Principal', 'Explorar', 'Tú']);
});

test('Explorar lists the pages in order, the server last, the same for players and admins', () => {
  const explorar = (user) => menuSections(user).find((s) => s.label === 'Explorar').items.map((i) => i.id);
  const order = ['games', 'library', 'players', 'calendar', 'achievements', 'stats', 'server'];
  assert.deepEqual(explorar({ is_admin: false }), order);
  assert.deepEqual(explorar({ is_admin: true }), order);
});

test('an admin also gets the panel, in a section of its own at the end', () => {
  assert.deepEqual(ids({ is_admin: true }).at(-1), 'admin');
  assert.equal(menuSections({ is_admin: true }).at(-1).label, 'Administración');
});

test('statistics are marked as work in progress and nothing else is', () => {
  const items = menuSections({ is_admin: true }).flatMap((s) => s.items);
  assert.deepEqual(items.filter((i) => i.wip).map((i) => i.id), ['stats']);
});

test('every id and address is unique', () => {
  const items = menuSections({ is_admin: true }).flatMap((s) => s.items);
  assert.equal(new Set(items.map((i) => i.id)).size, items.length);
  assert.equal(new Set(items.map((i) => i.href)).size, items.length);
});

test('an address highlights its item, the most specific one first', () => {
  assert.equal(activeItem(''), 'home');
  assert.equal(activeItem('#'), 'home');
  assert.equal(activeItem('#/activity'), 'activity');
  assert.equal(activeItem('#/stats'), 'stats');
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
