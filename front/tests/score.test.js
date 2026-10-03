import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseScore, scoreHue } from '../js/lib/score.js';

test('a rating is an integer from 1 to 100', () => {
  assert.equal(parseScore('1'), 1);
  assert.equal(parseScore(' 85 '), 85);
  assert.equal(parseScore('100'), 100);
});

test('an empty field means no rating', () => {
  assert.equal(parseScore(''), null);
  assert.equal(parseScore('   '), null);
  assert.equal(parseScore(undefined), null);
});

test('anything else is not a rating', () => {
  for (const text of ['0', '101', '-5', '7.5', 'abc', '1e1']) {
    assert.ok(Number.isNaN(parseScore(text)), text);
  }
});

test('the hue goes from red (worst) to green (best) and stays inside the scale', () => {
  assert.equal(scoreHue(1), 0);
  assert.equal(scoreHue(100), 125);
  assert.ok(scoreHue(50) > scoreHue(30) && scoreHue(30) > scoreHue(10));
  assert.equal(scoreHue(0), 0);
  assert.equal(scoreHue(500), 125);
});
