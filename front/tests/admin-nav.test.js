import assert from 'node:assert/strict';
import { test } from 'node:test';
import { GROUPS, HOME, hashFor, tabFromHash } from '../js/pages/admin/nav.js';

const valid = GROUPS.flatMap((g) => g.items);

test('every section has exactly one place in the sidebar', () => {
  assert.equal(new Set(valid).size, valid.length);
  assert.ok(valid.includes(HOME));
});

test('a section address goes there and back', () => {
  for (const tab of valid) assert.equal(tabFromHash(hashFor(tab), valid), tab);
});

test('the bare panel address and unknown sections are the home page', () => {
  assert.equal(tabFromHash('#/admin', valid), HOME);
  assert.equal(tabFromHash('#/admin/', valid), HOME);
  assert.equal(tabFromHash('#/admin/nothing', valid), HOME);
  assert.equal(tabFromHash('#/admin/users/extra', valid), HOME);
});
