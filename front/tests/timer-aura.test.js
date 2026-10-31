import assert from 'node:assert/strict';
import { test } from 'node:test';
import { auraColor } from '../js/lib/timer-aura.js';

const MIN = 60;

test('the aura starts teal and ends red', () => {
  assert.equal(auraColor(0), '168 70% 45%');
  assert.equal(auraColor(240 * MIN), '0 85% 56%');
});

test('it stays red after 4 hours and never goes below the start', () => {
  assert.equal(auraColor(10 * 3600), auraColor(240 * MIN));
  assert.equal(auraColor(-5), auraColor(0));
});

test('yellow shows up early: the hue is already yellow at 1:30', () => {
  assert.equal(auraColor(90 * MIN), '50 95% 52%');
});

test('between two stops the colour is blended', () => {
  assert.equal(auraColor(15 * MIN), '157 68% 45%');
});
