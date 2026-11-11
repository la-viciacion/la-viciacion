import assert from 'node:assert/strict';
import { test } from 'node:test';
import { auraColor } from '../js/lib/timer-aura.js';

const MIN = 60;

test('the aura starts green and ends red', () => {
  assert.equal(auraColor(0), '120 72% 46%');
  assert.equal(auraColor(240 * MIN), '0 85% 56%');
});

test('it stays red after 4 hours and never goes below the start', () => {
  assert.equal(auraColor(10 * 3600), auraColor(240 * MIN));
  assert.equal(auraColor(-5), auraColor(0));
});

test('yellow lands at 2:00', () => {
  assert.equal(auraColor(120 * MIN).split(' ')[0], '60');
});

test('the hue moves linearly: 30 degrees per hour', () => {
  const hue = (minutes) => Number(auraColor(minutes * MIN).split(' ')[0]);
  assert.equal(hue(60), 90);
  assert.equal(hue(180), 30);
});
