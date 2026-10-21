import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MAX_QUESTION, MAX_TURNS, SUGGESTIONS, SUGGESTION_COUNT, parseAnswer, pickSuggestions, toRequest } from '../js/lib/chat.js';

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
  assert.deepEqual(blocks[1].items.map((item) => item.map((p) => p.text).join('')), ['Ana: 3 h', 'Beto: 1 h']);
  assert.equal(blocks[2].type, 'ol'); // a numbered list is another list from a bulleted one
  assert.deepEqual(blocks[2].items.map((item) => item.map((p) => p.text).join('')), ['Otra']);
  assert.deepEqual(blocks[3], { type: 'p', parts: [{ text: 'Fin' }] });
});

test('*italic*, `code` and headings are understood, as the model writes them', () => {
  const [line] = parseAnswer('Tienes *The Legend of Zelda: Ocarina of Time* (sale el 5) y `game_id`.');
  assert.deepEqual(line.parts, [
    { text: 'Tienes ' }, { italic: true, text: 'The Legend of Zelda: Ocarina of Time' }, { text: ' (sale el 5) y ' },
    { code: true, text: 'game_id' }, { text: '.' },
  ]);
  const [h1, h3] = parseAnswer('# Ranking\n### Horas **de hoy**');
  assert.deepEqual(h1, { type: 'p', parts: [{ text: 'Ranking', bold: true }] });
  assert.deepEqual(h3.parts.map((p) => p.text), ['Horas ', 'de hoy']);
  assert.ok(h3.parts.every((p) => p.bold));
});

test('a list may use * or - or a dot, and an italic at the start of a line is not a bullet', () => {
  const [list] = parseAnswer('* Ana\n- Beto\n• Cris');
  assert.deepEqual([list.type, list.items.length], ['ul', 3]);
  const [paragraph] = parseAnswer('*Hades* es genial');
  assert.equal(paragraph.type, 'p');
  assert.deepEqual(paragraph.parts[0], { italic: true, text: 'Hades' });
});

test('a stray asterisk, an open marker or a space inside stays text', () => {
  for (const text of ['2 * 3 = 6', 'a * b * c', 'abierto *sin cerrar', '**', '****', '` `', 'precio: 5*']) {
    const [block] = parseAnswer(text);
    assert.equal(block.parts.map((p) => p.text).join(''), text, text);
    assert.ok(block.parts.every((p) => !p.bold && !p.italic), text);
  }
});

test('nothing else is interpreted: markup, links and tables stay text', () => {
  const [block] = parseAnswer('<img src=x onerror=alert(1)> [x](javascript:alert(1)) | a | b |');
  assert.deepEqual(block.parts, [{ text: '<img src=x onerror=alert(1)> [x](javascript:alert(1)) | a | b |' }]);
  assert.deepEqual(parseAnswer(''), []);
  assert.deepEqual(parseAnswer(null), []);
});

test('there is a long list of different questions, each one a question the box accepts', () => {
  assert.ok(SUGGESTIONS.length >= 40);
  assert.equal(new Set(SUGGESTIONS).size, SUGGESTIONS.length);
  for (const question of SUGGESTIONS) {
    assert.match(question, /^¿.+\?$/, question);
    assert.ok(question.length <= MAX_QUESTION, question);
  }
});

test('three different questions of the list are offered, and the list is left as it was', () => {
  const before = [...SUGGESTIONS];
  const picked = pickSuggestions();
  assert.equal(picked.length, SUGGESTION_COUNT);
  assert.equal(SUGGESTION_COUNT, 3);
  assert.equal(new Set(picked).size, 3);
  for (const question of picked) assert.ok(SUGGESTIONS.includes(question));
  assert.deepEqual(SUGGESTIONS, before);
});

test('the choice follows the random numbers, so it can differ every time', () => {
  assert.deepEqual(pickSuggestions(3, () => 0), SUGGESTIONS.slice(0, 3));
  assert.deepEqual(pickSuggestions(2, () => 0.999999), [SUGGESTIONS.at(-1), SUGGESTIONS.at(-2)]);
  const seen = new Set();
  for (let i = 0; i < 200; i++) pickSuggestions().forEach((question) => seen.add(question));
  assert.ok(seen.size > 3 * 5, 'across many starts, many different questions come up');
});

test('asking for more than there is, or for none, does not break', () => {
  assert.equal(pickSuggestions(1000).length, SUGGESTIONS.length);
  assert.deepEqual(pickSuggestions(0), []);
});
