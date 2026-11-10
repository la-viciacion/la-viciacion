import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CHANGELOG, KINDS, groups } from '../js/lib/changelog.js';

const texts = CHANGELOG.flatMap((e) => [e.title, ...e.items.map(([, text]) => text)]);
const key = (v) => v.split('.').map(Number);
const newer = (a, b) => key(a).reduce((r, n, i) => r || n - key(b)[i], 0) > 0;

test('the entries go from the newest to the oldest, one version each', () => {
  CHANGELOG.forEach((e, i) => {
    assert.match(e.version, /^\d+\.\d+$/);
    assert.match(e.date, /^\d{4}-\d{2}-\d{2}$/);
    const next = CHANGELOG[i + 1];
    if (!next) return;
    assert.equal(newer(e.version, next.version), true, `${e.title} is not newer than ${next.title}`);
    assert.equal(e.date >= next.date, true, `${e.title} is dated before ${next.title}`);
  });
});

test('every item has a known kind and a text that ends the way the others do', () => {
  for (const e of CHANGELOG) {
    assert.ok(e.items.length > 0, e.title);
    for (const [kind, text] of e.items) {
      assert.ok(kind in KINDS, `${kind} in ${e.title}`);
      assert.match(text, /\.$/, text);
    }
  }
});

// The changelog is for the players: the admin side, secrets, how things are unlocked and the app's insides never
// belong in it. This only catches the obvious words; the rule is the comment in lib/changelog.js.
test('nothing in it speaks of the admin side, secrets, how achievements are earned or the insides of the app', () => {
  const forbidden = /admin|secret|oculto|desbloque|huevo|easter|konami|clave|token|webhook|prometheus|migraci|base de datos|sentry|(?<![a-zñáéíóú])(api|bot)(?![a-zñáéíóú])/i;
  for (const text of texts) assert.doesNotMatch(text, forbidden, text);
});

test('the items of an entry are grouped by kind, in the order of the kinds', () => {
  const g = groups({ items: [['fix', 'a.'], ['new', 'b.'], ['fix', 'c.']] });
  assert.deepEqual(g.map((x) => [x.label, x.items]), [['Nuevo', ['b.']], ['Arreglo', ['a.', 'c.']]]);
});
