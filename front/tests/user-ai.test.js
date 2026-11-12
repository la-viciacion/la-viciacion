import assert from 'node:assert/strict';
import { test } from 'node:test';
import { keyText, looksLikeKey, modelLabel, payerText } from '../js/lib/user-ai.js';

test('a model reads with its tier and its price per million tokens, or only its tier without a price', () => {
  assert.match(modelLabel({ id: 'gpt-4.1-mini', tier: 'economico', input_per_million: 0.4, output_per_million: 1.6 }), /^gpt-4\.1-mini · económico · 0,40.*1,60.* por millón$/);
  assert.equal(modelLabel({ id: 'gpt-9', tier: 'sin_precio', input_per_million: null, output_per_million: null }), 'gpt-9 · sin precio conocido');
  assert.match(modelLabel({ id: 'o1-pro', tier: 'caro', input_per_million: 150, output_per_million: 600 }), /caro/);
});

test('who pays is said in one sentence for every state', () => {
  assert.match(payerText({ available: false }), /no está disponible/);
  assert.match(payerText({ available: true, needs_key: true }), /propia clave/);
  assert.match(payerText({ available: true, needs_key: false, paid_by: 'user' }), /tu clave/);
  assert.match(payerText({ available: true, paid_by: 'group', mode: 'group_only' }), /tengas clave o no/);
  assert.match(payerText({ available: true, paid_by: 'group', mode: 'user_or_group' }), /mientras no guardes tu propia clave/);
});

test('the key is shown by its last characters and never by itself', () => {
  assert.equal(keyText({ hint: 'a1b2' }), 'Clave guardada, termina en …a1b2');
});

test('only what looks like an OpenAI key is sent', () => {
  assert.equal(looksLikeKey(' sk-proj-AbCdEfGhIjKlMnOpQrSt '), true);
  for (const bad of ['', 'hello', 'sk-short', 'sk- con espacios dentro de la clave', 'AIzaSyFake0123456789012345']) assert.equal(looksLikeKey(bad), false, bad);
});
