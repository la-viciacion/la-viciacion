import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HOME, SECTIONS, TAB_IDS, hashFor, sectionOf, tabFromHash } from '../js/pages/admin/nav.js';

test('every tab belongs to exactly one section', () => {
  assert.equal(new Set(TAB_IDS).size, TAB_IDS.length);
  assert.ok(TAB_IDS.includes(HOME));
  for (const tab of TAB_IDS) assert.equal(SECTIONS.filter((s) => s.tabs.includes(tab)).length, 1);
});

test('the section of a tab is the one that lists it', () => {
  assert.equal(sectionOf('users').label, 'Gestión de datos');
  assert.equal(sectionOf('announce').label, 'Notificaciones');
  assert.equal(sectionOf('nothing'), undefined);
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
