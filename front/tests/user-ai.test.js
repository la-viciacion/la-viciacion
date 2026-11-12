import assert from 'node:assert/strict';
import { test } from 'node:test';
import { costNote, keyText, looksLikeKey, modelLabel } from '../js/lib/user-ai.js';

test('a model reads with its tier and its price per million tokens, or only its tier without a price', () => {
  assert.match(modelLabel({ id: 'gpt-4.1-mini', tier: 'economico', input_per_million: 0.4, output_per_million: 1.6 }), /^gpt-4\.1-mini · económico · 0,40.*1,60.* por millón$/);
  assert.equal(modelLabel({ id: 'gpt-9', tier: 'sin_precio', input_per_million: null, output_per_million: null }), 'gpt-9 · sin precio conocido');
  assert.match(modelLabel({ id: 'o1-pro', tier: 'caro', input_per_million: 150, output_per_million: 600 }), /caro/);
});

const on = (extra) => ({ available: true, needs_key: false, paid_by: 'group', mode: 'group_then_user', blocked: null, ...extra });
const needs = (extra) => on({ paid_by: null, needs_key: true, mode: 'user_only', ...extra });
const none = { has_key: false };
const mine = { has_key: true };

test('where the cost goes is a quiet note in words of cost, never of paying', () => {
  const cases = [
    costNote({ chat: on(), guide: needs(), key: none }),
    costNote({ chat: on(), guide: on({ paid_by: 'user', mode: 'user_only' }), key: mine }),
    costNote({ chat: on(), guide: on(), key: none }),
    costNote({ chat: on(), guide: on(), key: mine }),
    costNote({ chat: on({ paid_by: 'user', blocked: 'group' }), guide: on({ paid_by: 'user', blocked: 'group' }), key: mine }),
    costNote({ chat: on({ mode: 'group_only' }), guide: on({ mode: 'group_only' }), key: none }),
    costNote({ chat: { available: false }, guide: needs(), key: none }),
    costNote({ chat: needs(), guide: needs(), key: none }),
  ];
  for (const note of cases) assert.doesNotMatch(note, /\bpag(a|o|ar|ado)\b/i, note);
  assert.match(cases[0], /coste del chat lo cubre el grupo mientras haya presupuesto este mes; después necesitarás tu propia clave\. La guía.*cuesta más: funciona con tu propia clave/);
  assert.match(cases[1], /coste del chat lo cubre el grupo.*después seguirá con tu clave.*El coste de la guía va a tu cuenta de OpenAI/);
  assert.match(cases[2], /^El coste del chat y de la guía lo cubre el grupo mientras haya presupuesto este mes; después necesitarás tu propia clave\.$/);
  assert.match(cases[3], /después seguirá con tu clave, a tu cuenta de OpenAI/);
  assert.match(cases[4], /Se ha agotado el presupuesto del grupo este mes: de momento el coste del chat y de la guía va a tu cuenta de OpenAI/);
  assert.match(cases[5], /tengas clave o no/);
  assert.match(cases[6], /^El chat no está disponible ahora mismo\. La guía.*propia clave/);
  assert.match(cases[7], /^El chat y la guía funcionan con tu propia clave\.$/);
});

test('the group comes first and the own key is only the way on, so a key does not move the chat off the group', () => {
  const note = costNote({ chat: on(), guide: on(), key: mine });
  assert.match(note, /lo cubre el grupo mientras haya presupuesto/);
  assert.doesNotMatch(note, /^Con tu clave/);
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
