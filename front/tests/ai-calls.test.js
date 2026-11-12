import assert from 'node:assert/strict';
import { test } from 'node:test';
import { featureLabel, perCall, sourceLabel, statusLabel, tokens, unpricedNote } from '../js/lib/ai-calls.js';

test('the tokens of a month are read in millions and the small ones with thousands separators', () => {
  assert.equal(tokens(999), '999');
  assert.equal(tokens(1500000), '1,5 M');
  assert.match(tokens(12345), /^12\.?345$/);
});

test('an unknown feature, source or status is shown as it came', () => {
  assert.equal(featureLabel('guide'), 'Guía de juego');
  assert.equal(sourceLabel('group'), 'Clave del grupo');
  assert.equal(statusLabel('limited'), 'Frenadas por el límite');
  assert.equal(featureLabel('new'), 'new');
});

test('the note on unpriced calls is singular or plural and absent when every call has a price', () => {
  assert.equal(unpricedNote({ unpriced: 0 }), null);
  assert.match(unpricedNote({ unpriced: 1 }), /^1 llamada sin precio/);
  assert.match(unpricedNote({ unpriced: 3 }), /^3 llamadas sin precio/);
});

test('the average cost of a call is none without calls', () => {
  assert.equal(perCall({ calls: 0, cost: 0 }), null);
  assert.equal(perCall({ calls: 4, cost: 1 }), 0.25);
});
