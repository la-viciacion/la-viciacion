import assert from 'node:assert/strict';
import { test } from 'node:test';
import { progressPercent, progressText } from '../js/lib/achievement-progress.js';

test('the bar is a whole percent of the goal', () => {
  assert.equal(progressPercent({ current: 35, target: 100 }), 35);
  assert.equal(progressPercent({ current: 1, target: 3 }), 33);
  assert.equal(progressPercent({ current: 100, target: 100 }), 100);
});

test('it never goes past full and a little progress still shows', () => {
  assert.equal(progressPercent({ current: 250, target: 200 }), 100);
  assert.equal(progressPercent({ current: 0.4, target: 1000 }), 1);
});

test('no progress is an empty bar', () => {
  assert.equal(progressPercent({ current: 0, target: 10 }), 0);
  assert.equal(progressPercent({ current: 5, target: 0 }), 0);
});

test('the text says how far, without a unit', () => {
  assert.equal(progressText({ current: 35, target: 100 }), '35 / 100');
  assert.equal(progressText({ current: 12.5, target: 100 }), '12,5 / 100');
});
