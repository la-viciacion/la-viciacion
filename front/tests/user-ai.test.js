import assert from 'node:assert/strict';
import { test } from 'node:test';
import { costNote, keyText, looksLikeKey, modelLabel } from '../js/lib/user-ai.js';

test('a model reads with its tier and its price per million tokens, or only its tier without a price', () => {
  assert.match(modelLabel({ id: 'gpt-4.1-mini', tier: 'economico', input_per_million: 0.4, output_per_million: 1.6 }), /^gpt-4\.1-mini · económico · 0,40.*1,60.* por millón$/);
  assert.equal(modelLabel({ id: 'gpt-9', tier: 'sin_precio', input_per_million: null, output_per_million: null }), 'gpt-9 · sin precio conocido');
  assert.match(modelLabel({ id: 'o1-pro', tier: 'caro', input_per_million: 150, output_per_million: 600 }), /caro/);
});

const on = (extra) => ({ available: true, needs_key: false, paid_by: 'group', mode: 'user_or_group', ...extra });

test('where the cost goes is a quiet note in words of cost, never of paying', () => {
  const cases = [
    costNote({ chat: on(), guide: on({ paid_by: null, needs_key: true, mode: 'user_only' }) }),
    costNote({ chat: on({ paid_by: 'user' }), guide: on({ paid_by: 'user', mode: 'user_only' }) }),
    costNote({ chat: on(), guide: on() }),
    costNote({ chat: on({ mode: 'group_only' }), guide: on({ mode: 'group_only' }) }),
    costNote({ chat: { available: false }, guide: on({ paid_by: null, needs_key: true }) }),
  ];
  for (const note of cases) assert.doesNotMatch(note, /\bpag(a|o|ar|ado)\b/i, note);
  assert.match(cases[0], /coste del chat lo cubre el grupo.*guía.*cuesta más.*tu propia clave/);
  assert.match(cases[1], /Con tu clave, el coste.*tu cuenta de OpenAI/);
  assert.match(cases[2], /lo cubre el grupo; con tu propia clave pasa a tu cuenta/);
  assert.match(cases[3], /tengas clave o no/);
  assert.match(cases[4], /El chat no está disponible ahora mismo\..*propia clave/);
});

test('a note says nothing when there is nothing to say', () => {
  assert.equal(costNote({ chat: { available: false }, guide: { available: false } }), 'El chat no está disponible ahora mismo. La guía de cada juego no está disponible ahora mismo.');
});

test('the key is shown by its last characters and never by itself', () => {
  assert.equal(keyText({ hint: 'a1b2' }), 'Clave guardada, termina en …a1b2');
});

test('only what looks like an OpenAI key is sent', () => {
  assert.equal(looksLikeKey(' sk-proj-AbCdEfGhIjKlMnOpQrSt '), true);
  for (const bad of ['', 'hello', 'sk-short', 'sk- con espacios dentro de la clave', 'AIzaSyFake0123456789012345']) assert.equal(looksLikeKey(bad), false, bad);
});
