import assert from 'node:assert/strict';
import { test } from 'node:test';
import { featureLabel, freeNote, googleNote, perCall, sourceLabel, statusLabel, tokens, unpricedNote } from '../js/lib/ai-calls.js';

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
  assert.equal(featureLabel('welcome'), 'Bienvenida del grupo');
  assert.equal(featureLabel('notice'), 'Avisos con IA');
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

test('a call to Google is said to be an estimate, and a record with none says nothing', () => {
  assert.match(googleNote([{ name: 'openai/gpt-4.1-mini', calls: 3 }, { name: 'google/gemini-2.5-flash', calls: 1 }]), /solo una estimación.*0 US\$/);
  assert.equal(googleNote([{ name: 'openai/gpt-4.1-mini', calls: 3 }]), null);
  assert.equal(googleNote([{ name: 'google/gemini-2.5-flash', calls: 0 }]), null);
});

test('calls on a free plan are not a Google estimate to worry about, and are said to have cost nothing', () => {
  assert.equal(googleNote([{ name: 'google/gemini-2.5-flash', calls: 2, free_calls: 2 }]), null);
  assert.match(googleNote([{ name: 'google/gemini-2.5-flash', calls: 2, free_calls: 1 }]), /márcalo/);
  assert.equal(freeNote({ free_calls: 0 }), null);
  assert.match(freeNote({ free_calls: 1 }), /1 llamada con una clave de plan gratuito.*real fue 0 US\$/);
  assert.match(freeNote({ free_calls: 3 }), /3 llamadas/);
});
