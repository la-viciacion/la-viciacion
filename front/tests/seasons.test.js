import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ALL, choices } from '../js/lib/seasons.js';

test('the season choices end with the total', () => {
  assert.deepEqual(choices([2026, 2025]).map((c) => c.label), ['2026', '2025', 'Total']);
  assert.equal(choices([2026]).at(-1).value, ALL);
});
