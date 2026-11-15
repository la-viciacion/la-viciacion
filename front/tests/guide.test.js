import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DEFAULT_LEVEL, DEFAULT_MODE, LEVELS, MODES, conversationOf, forgetConversations, toGuideRequest } from '../js/lib/guide.js';

test('the request is the chat\'s plus the level of help', () => {
  const body = toGuideRequest([{ role: 'user', content: 'a' }, { role: 'assistant', content: 'b' }], ' hola ', 'hint');
  assert.equal(body.message, 'hola');
  assert.equal(body.level, 'hint');
  assert.equal(body.history.length, 2);
});

test('an unknown level is the softest one', () => {
  assert.equal(toGuideRequest([], 'x', 'all').level, DEFAULT_LEVEL);
  assert.equal(LEVELS[0].id, DEFAULT_LEVEL);
});

test('each game keeps its own conversation until they are forgotten', () => {
  forgetConversations();
  conversationOf('g1').turns.push({ role: 'user', content: 'q' });
  assert.equal(conversationOf('g1').turns.length, 1);
  assert.equal(conversationOf('g2').turns.length, 0);
  forgetConversations();
  assert.equal(conversationOf('g1').turns.length, 0);
});

test('the request carries the way of playing and an unknown one is the main story', () => {
  assert.equal(toGuideRequest([], 'x', 'hint', 'completionist').mode, 'completionist');
  assert.equal(toGuideRequest([], 'x', 'hint', 'extras').mode, 'extras');
  assert.equal(toGuideRequest([], 'x', 'hint', 'free').mode, 'free');
  assert.equal(toGuideRequest([], 'x', 'hint', 'speedrun').mode, DEFAULT_MODE);
  assert.equal(MODES[0].id, DEFAULT_MODE);
  assert.equal(conversationOf('new-game').mode, DEFAULT_MODE);
});
