import assert from 'node:assert/strict';
import { test } from 'node:test';
import { KONAMI_KEYS, KONAMI_SWIPES, keyStep, sequenceMatcher, skinFor, swipeStep, tapCounter } from '../js/lib/easter-eggs.js';

const feed = (matcher, steps) => steps.map((s) => matcher(s));

test('the Konami code matches only when its last step arrives', () => {
  const hits = feed(sequenceMatcher(KONAMI_KEYS), KONAMI_KEYS);
  assert.deepEqual(hits.slice(0, -1).filter(Boolean), []);
  assert.equal(hits.at(-1), true);
});

test('an extra step before the code does not hide it, a wrong one inside does', () => {
  assert.equal(feed(sequenceMatcher(KONAMI_KEYS), ['up', ...KONAMI_KEYS]).at(-1), true);
  const broken = [...KONAMI_KEYS.slice(0, 5), 'x', ...KONAMI_KEYS.slice(5)];
  assert.equal(feed(sequenceMatcher(KONAMI_KEYS), broken).at(-1), false);
});

test('a pause longer than the gap starts the code over', () => {
  let t = 0;
  const matcher = sequenceMatcher(KONAMI_KEYS, { now: () => t });
  for (const step of KONAMI_KEYS.slice(0, 5)) matcher(step);
  t = 6000;
  assert.equal(feed(matcher, KONAMI_KEYS.slice(5)).at(-1), false);
});

test('it can be done again after it matched', () => {
  const matcher = sequenceMatcher(KONAMI_KEYS);
  feed(matcher, KONAMI_KEYS);
  assert.equal(feed(matcher, KONAMI_KEYS).at(-1), true);
});

test('keys become steps, and modifiers are skipped', () => {
  assert.equal(keyStep('ArrowUp'), 'up');
  assert.equal(keyStep('B'), 'b');
  assert.equal(keyStep('Shift'), null);
});

test('gestures become a direction, or a tap when they barely moved', () => {
  assert.equal(swipeStep(5, -8), 'tap');
  assert.equal(swipeStep(0, -120), 'up');
  assert.equal(swipeStep(10, 90), 'down');
  assert.equal(swipeStep(-80, 20), 'left');
  assert.equal(swipeStep(80, -20), 'right');
});

test('the swipes of a phone complete the same code', () => {
  assert.equal(feed(sequenceMatcher(KONAMI_SWIPES), KONAMI_SWIPES).at(-1), true);
});

test('seven taps inside the window count, slower ones do not', () => {
  let t = 0;
  const taps = tapCounter({ now: () => t });
  const results = [];
  for (let i = 0; i < 7; i++) { results.push(taps()); t += 400; }
  assert.deepEqual(results, [false, false, false, false, false, false, true]);

  const slow = tapCounter({ now: () => t });
  const slowResults = [];
  for (let i = 0; i < 10; i++) { slowResults.push(slow()); t += 1000; }
  assert.equal(slowResults.includes(true), false);
});

test('the logo wears a costume only in its week', () => {
  assert.equal(skinFor(new Date(2026, 9, 24)), '');
  assert.equal(skinFor(new Date(2026, 9, 25)), 'halloween');
  assert.equal(skinFor(new Date(2026, 9, 31)), 'halloween');
  assert.equal(skinFor(new Date(2026, 10, 1)), '');
  assert.equal(skinFor(new Date(2026, 11, 23)), '');
  assert.equal(skinFor(new Date(2026, 11, 24)), 'christmas');
  assert.equal(skinFor(new Date(2026, 11, 31)), 'christmas');
  assert.equal(skinFor(new Date(2027, 0, 1)), '');
});
