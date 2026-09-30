import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseHours } from '../js/lib/hours.js';

test('parseHours accepts whole hours in range', () => {
  assert.equal(parseHours('1'), 1);
  assert.equal(parseHours(' 6 '), 6);
  assert.equal(parseHours('24'), 24);
});

test('an empty field means the default', () => {
  assert.equal(parseHours(''), null);
  assert.equal(parseHours('   '), null);
});

test('parseHours rejects minutes, decimals and out-of-range values', () => {
  for (const bad of ['0', '25', '-1', '2.5', '2,5', '1:30', 'abc', '1e1']) {
    assert.equal(parseHours(bad), undefined, bad);
  }
});
