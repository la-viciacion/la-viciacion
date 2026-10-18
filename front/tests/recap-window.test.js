import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installStorage } from './dom.js';

installStorage();
const { WINDOW_DAYS, hasSeen, markSeen, windowPeriod } = await import('../js/lib/recap-window.js');

test('the recap is offered from the 1st to the 5th, for the month that ended', () => {
  assert.equal(WINDOW_DAYS, 5);
  assert.equal(windowPeriod(new Date(2026, 9, 1)), '2026-09');
  assert.equal(windowPeriod(new Date(2026, 9, 5, 23, 59)), '2026-09');
  assert.equal(windowPeriod(new Date(2026, 9, 6)), null);
  assert.equal(windowPeriod(new Date(2026, 9, 18)), null);
  assert.equal(windowPeriod(new Date(2026, 9, 31)), null);
});

test('in January it is the December of the year before', () => {
  assert.equal(windowPeriod(new Date(2027, 0, 2)), '2026-12');
});

test('a period is seen once it has been marked, and only that period', () => {
  assert.equal(hasSeen('2026-09'), false);
  markSeen('2026-09');
  assert.equal(hasSeen('2026-09'), true);
  assert.equal(hasSeen('2026-10'), false);
});

test('without storage nothing breaks: it is just never remembered', () => {
  const saved = globalThis.localStorage;
  globalThis.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  assert.equal(hasSeen('2026-08'), false);
  assert.doesNotThrow(() => markSeen('2026-08'));
  globalThis.localStorage = saved;
});
