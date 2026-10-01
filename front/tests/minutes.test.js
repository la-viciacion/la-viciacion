import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MIN_MINUTES, parseMinutes } from '../js/lib/minutes.js';

test('parseMinutes accepts whole minutes in range', () => {
  assert.equal(parseMinutes('10'), 10);
  assert.equal(parseMinutes(' 30 '), 30);
  assert.equal(parseMinutes('120'), 120);
});

test('an empty field means the default', () => {
  assert.equal(parseMinutes(''), null);
  assert.equal(parseMinutes('   '), null);
});

test('the notification can never refresh more often than every 10 minutes', () => {
  assert.equal(MIN_MINUTES, 10);
  for (const bad of ['0', '1', '5', '9']) assert.equal(parseMinutes(bad), undefined, bad);
});

test('parseMinutes rejects decimals, text and out-of-range values', () => {
  for (const bad of ['121', '-10', '10.5', '10,5', '1:30', 'abc', '1e1']) {
    assert.equal(parseMinutes(bad), undefined, bad);
  }
});
