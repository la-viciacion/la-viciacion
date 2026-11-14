import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ABOUT, PROVIDERS, costNote, hasAnyKey, keyText, looksLikeKey, modelLabel, providerName } from '../js/lib/user-ai.js';

test('a model reads with its tier and its price per million tokens, or only its tier without a price', () => {
  assert.match(modelLabel({ id: 'gpt-4.1-mini', tier: 'economico', input_per_million: 0.4, output_per_million: 1.6 }), /^gpt-4\.1-mini · económico · 0,40.*1,60.* por millón$/);
  assert.equal(modelLabel({ id: 'gpt-9', tier: 'sin_precio', input_per_million: null, output_per_million: null }), 'gpt-9 · sin precio conocido');
  assert.match(modelLabel({ id: 'o1-pro', tier: 'caro', input_per_million: 150, output_per_million: 600 }), /caro/);
});

const on = (extra) => ({ available: true, needs_key: false, paid_by: 'group', mode: 'group_then_user', blocked: null, locked: false, ...extra });
const needs = (extra) => on({ paid_by: null, needs_key: true, mode: 'user_only', ...extra });
const none = { openai: { has_key: false }, google: { has_key: false } };
const mine = { openai: { has_key: false }, google: { has_key: true } }; // a key of any provider counts

test('where the cost goes is a quiet note in words of cost, never of paying', () => {
  const cases = [
    costNote({ chat: on(), guide: needs(), keys: none }),
    costNote({ chat: on(), guide: on({ paid_by: 'user', mode: 'user_only' }), keys: mine }),
    costNote({ chat: on(), guide: on(), keys: none }),
    costNote({ chat: on(), guide: on(), keys: mine }),
    costNote({ chat: on({ paid_by: 'user', blocked: 'user' }), guide: on({ paid_by: 'user', blocked: 'user' }), keys: mine }),
    costNote({ chat: on({ mode: 'group_only' }), guide: on({ mode: 'group_only' }), keys: none }),
    costNote({ chat: { available: false }, guide: needs(), keys: none }),
    costNote({ chat: needs(), guide: needs(), keys: none }),
  ];
  for (const note of cases) assert.doesNotMatch(note, /\bpag(a|o|ar|ado)\b/i, note);
  assert.match(cases[0], /coste del chat lo cubre el grupo mientras haya saldo; después necesitarás tu propia clave\. La guía.*cuesta más: funciona con tu propia clave/);
  assert.match(cases[1], /coste del chat lo cubre el grupo.*después seguirá con tu clave.*El coste de la guía va a tu cuenta del proveedor de tu clave/);
  assert.match(cases[2], /^El coste del chat y de la guía lo cubre el grupo mientras haya saldo; después necesitarás tu propia clave\.$/);
  assert.match(cases[3], /después seguirá con tu clave, a tu cuenta del proveedor/);
  assert.match(cases[4], /Ya no puedes usar la clave del grupo: de momento el coste del chat y de la guía va a tu cuenta del proveedor de tu clave/);
  assert.match(cases[5], /tengas clave o no/);
  assert.match(cases[6], /^El chat no está disponible ahora mismo\. La guía.*propia clave/);
  assert.match(cases[7], /^El chat y la guía funcionan con tu propia clave\.$/);
});

test('a locked session is told that the key is there and that the password opens it, not that a key is needed', () => {
  const note = costNote({ chat: needs({ locked: true, needs_key: false }), guide: needs({ locked: true, needs_key: false }), keys: mine });
  assert.match(note, /El chat y la guía funcionan con tu propia clave, que está bloqueada en esta sesión: escribe tu contraseña/);
  assert.doesNotMatch(note, /necesitarás/);
});

test('the group comes first and the own key is only the way on, so a key does not move the chat off the group', () => {
  const note = costNote({ chat: on(), guide: on(), keys: mine });
  assert.match(note, /lo cubre el grupo mientras haya saldo/);
  assert.doesNotMatch(note, /^Con tu clave/);
});

test('a note says nothing when there is nothing to say', () => {
  assert.equal(costNote({ chat: { available: false }, guide: { available: false } }), 'El chat no está disponible ahora mismo. La guía de cada juego no está disponible ahora mismo.');
});

test('any provider\'s key counts as having one', () => {
  assert.equal(hasAnyKey(none), false);
  assert.equal(hasAnyKey(mine), true);
  assert.equal(hasAnyKey(undefined), false);
});

test('the key is shown by its last characters while unlocked, only as saved when not, and never by itself', () => {
  assert.equal(keyText({ hint: 'a1b2' }), 'Clave guardada, termina en …a1b2');
  assert.equal(keyText({ hint: null }), 'Clave guardada');
});

const KEYS = {
  openai: 'sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789',
  anthropic: 'sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789',
  openrouter: 'sk-or-v1-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdef',
  google: 'AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz0123456',
};

test('every provider recognizes its own kind of key and no other', () => {
  assert.deepEqual(PROVIDERS.map((p) => p.id), ['openai', 'anthropic', 'google', 'openrouter']);
  for (const [provider, key] of Object.entries(KEYS)) {
    assert.equal(looksLikeKey(provider, ` ${key} `), true, provider);
    for (const other of Object.keys(KEYS).filter((o) => o !== provider)) assert.equal(looksLikeKey(other, key), false, `${provider}'s key is not ${other}'s`);
    for (const bad of ['', 'hello', 'sk-short', 'sk- con espacios dentro de la clave']) assert.equal(looksLikeKey(provider, bad), false, `${provider}: ${bad}`);
  }
  assert.equal(looksLikeKey('nobody', KEYS.openai), false);
});

test('every provider has a name, a place to make the key and advice about its limit', () => {
  for (const provider of PROVIDERS) {
    assert.ok(provider.name && provider.placeholder && provider.url.startsWith('https://') && provider.where && provider.limit.length > 20, provider.id);
    assert.equal(providerName(provider.id), provider.name);
  }
  assert.equal(providerName('unknown'), 'unknown');
});

test('what the chat and the guide do is explained, with what each costs and what the guide adds, and its limit', () => {
  const { chat, guide } = ABOUT;
  assert.ok(chat.what.length >= 3 && guide.what.length >= 3);
  assert.match(chat.cost, /fracción de céntimo/);
  assert.match(guide.cost, /búsquedas en internet.*se cobran aparte.*varias veces lo que una del chat/);
  assert.match(guide.addsTitle, /ChatGPT/);
  assert.ok(guide.adds.length >= 3);
  assert.match(guide.adds.join(' '), /qué juego|de qué juego/);
  assert.match(guide.adds.join(' '), /destripes/);
  assert.match(guide.limit, /No sabe más que ChatGPT/, 'it says what it does not do, not only what it does');
});

test('it speaks of cost and never of paying, and names nothing a player is not meant to discover', () => {
  const text = JSON.stringify(ABOUT);
  assert.doesNotMatch(text, /\bpag(a|o|ar|ado)\b/i);
  assert.doesNotMatch(text, /logro[^.]*(se desbloquea|desbloquear|umbral|aura)/i);
});
