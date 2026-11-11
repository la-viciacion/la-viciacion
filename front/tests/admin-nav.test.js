import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HOME, MOVED, SECTIONS, TAB_IDS, hashFor, sectionOf, tabFromHash } from '../js/pages/admin/nav.js';

test('every tab belongs to exactly one section', () => {
  assert.equal(new Set(TAB_IDS).size, TAB_IDS.length);
  assert.ok(TAB_IDS.includes(HOME));
  for (const tab of TAB_IDS) assert.equal(SECTIONS.filter((s) => s.tabs.includes(tab)).length, 1);
});

test('the section of a tab is the one that lists it', () => {
  assert.equal(sectionOf('games').label, 'Catálogo');
  assert.equal(sectionOf('users').label, 'Jugadores');
  assert.equal(sectionOf('awards').label, 'Jugadores');
  for (const tab of ['challenges', 'proposals', 'polls', 'announce']) assert.equal(sectionOf(tab).label, 'Comunidad', tab);
  for (const tab of ['sends', 'channels', 'recap']) assert.equal(sectionOf(tab).label, 'Notificaciones', tab);
  for (const tab of ['ai', 'chat', 'aiusage']) assert.equal(sectionOf(tab).label, 'IA', tab);
  for (const tab of ['costs', 'backup', 'audit']) assert.equal(sectionOf(tab).label, 'Sistema', tab);
  assert.equal(sectionOf('nothing'), undefined);
});

test('no section has more tabs than fit in a row on a phone', () => {
  for (const section of SECTIONS) assert.ok(section.tabs.length <= 5, section.label);
});

test('an old address of a tab that was folded into another goes to the one that took its place', () => {
  assert.equal(tabFromHash('#/admin/services'), 'channels');
  for (const [old, now] of Object.entries(MOVED)) {
    assert.ok(!TAB_IDS.includes(old), old); // it is no tab any more
    assert.ok(TAB_IDS.includes(now), now);
  }
});

test('a tab address goes there and back', () => {
  for (const tab of TAB_IDS) assert.equal(tabFromHash(hashFor(tab)), tab);
});

test('the bare panel address and unknown tabs are the home page', () => {
  assert.equal(tabFromHash('#/admin'), HOME);
  assert.equal(tabFromHash('#/admin/'), HOME);
  assert.equal(tabFromHash('#/admin/nothing'), HOME);
  assert.equal(tabFromHash('#/admin/users/extra'), HOME);
});
