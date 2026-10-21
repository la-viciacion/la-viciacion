import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MAX_QUESTION, MAX_TURNS, parseAnswer, toRequest } from '../js/lib/chat.js';

const turn = (role, content, extra = {}) => ({ role, content, ...extra });

test('the request carries the question trimmed and cut to the limit', () => {
  assert.equal(toRequest([], '  hola  ').message, 'hola');
  assert.equal(toRequest([], 'x'.repeat(MAX_QUESTION + 50)).message.length, MAX_QUESTION);
});

test('the history is the last turns, without the failed questions and the errors', () => {
  const turns = [
    turn('user', 'a'), turn('assistant', 'b'),
    turn('user', 'c', { failed: true }), turn('error', 'Algo falló'),
    turn('user', 'd'), turn('assistant', 'e'),
  ];
  assert.deepEqual(toRequest(turns, 'f').history.map((t) => t.content), ['a', 'b', 'd', 'e']);
});

test('the history never has more than the API keeps and starts with a question', () => {
  const turns = Array.from({ length: MAX_TURNS + 5 }, (_, i) => (i % 2 ? turn('assistant', `a${i}`) : turn('user', `q${i}`)));
  const { history } = toRequest(turns, 'siguiente');
  assert.ok(history.length <= MAX_TURNS);
  assert.equal(history[0].role, 'user');
});

test('a long turn is cut to what the API accepts', () => {
  const { history } = toRequest([turn('user', 'q'), turn('assistant', 'y'.repeat(5000))], 'x');
  assert.equal(history[1].content.length, 2000);
});

test('an answer is split into paragraphs, lists and bold text', () => {
  const blocks = parseAnswer('Ana va **primera**.\n\n- Ana: 3 h\n- Beto: 1 h\n1. Otra\nFin');
  assert.deepEqual(blocks[0], { type: 'p', parts: [{ text: 'Ana va ' }, { bold: true, text: 'primera' }, { text: '.' }] });
  assert.equal(blocks[1].type, 'ul');
  assert.deepEqual(blocks[1].items.map((item) => item.map((p) => p.text).join('')), ['Ana: 3 h', 'Beto: 1 h', 'Otra']);
  assert.deepEqual(blocks[2], { type: 'p', parts: [{ text: 'Fin' }] });
});

test('nothing else is interpreted: markup stays text', () => {
  const [block] = parseAnswer('<img src=x onerror=alert(1)> **a** `code` # no');
  assert.equal(block.parts[0].text, '<img src=x onerror=alert(1)> ');
  assert.deepEqual(parseAnswer(''), []);
  assert.deepEqual(parseAnswer(null), []);
});
