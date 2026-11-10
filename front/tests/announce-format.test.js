import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BODY_MAX, MESSAGE_MAX, blocks, drawnLength, inline } from '../js/lib/announce-format.js';

const NOTES = `## Novedades de la 2.40

Una **gran** versión con _varias_ cosas:

- Nuevo: la página de *Novedades*
  - con sub-puntos
1. Primero

> Un aviso

---
Más en [la guía](https://example.com/guia).`;

test('release notes become headings, paragraphs, bullets with their level, numbered items, quotes and rules', () => {
  const types = blocks(NOTES).map((b) => b.type);
  assert.deepEqual(types, ['heading', 'gap', 'p', 'gap', 'item', 'item', 'item', 'gap', 'quote', 'gap', 'rule', 'p']);
  const items = blocks(NOTES).filter((b) => b.type === 'item');
  assert.deepEqual(items.map((i) => [i.mark, i.level]), [['•', 0], ['◦', 1], ['1.', 0]]);
});

test('inline marks become pieces with a style, and a link keeps its address only when it is http(s)', () => {
  assert.deepEqual(inline('una **gran** `x` y *dos*'), [
    { text: 'una ' }, { text: 'gran', style: 'b' }, { text: ' ' }, { text: 'x', style: 'code' }, { text: ' y ' }, { text: 'dos', style: 'i' },
  ]);
  assert.deepEqual(inline('[a](https://x.org) [b](javascript:alert(1))'), [{ text: 'a', href: 'https://x.org' }, { text: ' ' }, { text: 'b' }, { text: ')' }]);
});

test('snake_case and stray asterisks are not formatting', () => {
  assert.deepEqual(inline('snake_case_name y 2 * 3 * 4'), [{ text: 'snake_case_name y 2 * 3 * 4' }]);
});

test('a heading does not nest bold, and an unclosed code block still shows what it holds', () => {
  assert.deepEqual(blocks('# Un **título**')[0].pieces, [{ text: 'Un título' }]);
  assert.deepEqual(blocks('```\nsin cerrar'), [{ type: 'code', text: 'sin cerrar' }]);
});

test('HTML typed in the message stays text', () => {
  assert.deepEqual(blocks('<script>x</script>')[0].pieces, [{ text: '<script>x</script>' }]);
});

test('the drawn length counts a separator as the ten characters Telegram shows', () => {
  assert.equal(drawnLength('t', '---'), 1 + 2 + 10);
  assert.ok(drawnLength('t', '---\n'.repeat(700)) > MESSAGE_MAX);
  assert.ok(drawnLength('t', 'a'.repeat(BODY_MAX)) < MESSAGE_MAX + 100);
});
