import assert from 'node:assert/strict';
import { test } from 'node:test';
import { budgetLine, capLabel, isNearly, isSpent, parseCap, spentShare } from '../js/lib/ai-budget.js';

test('no cap is no limit, zero is nothing of the groups key and any other is dollars', () => {
  assert.equal(capLabel(null), 'sin límite');
  assert.equal(capLabel(0), 'sin IA del grupo');
  assert.match(capLabel(5), /^5,00.*US\$$/);
});

test('the share of a budget that is spent never goes over the bar and is zero without a cap', () => {
  assert.equal(spentShare(2, 4), 50);
  assert.equal(spentShare(9, 4), 100);
  assert.equal(spentShare(3, 0), 0);
});

test('a budget is spent when it reaches its cap and nearly spent from eighty percent', () => {
  assert.equal(isSpent(5, 5), true);
  assert.equal(isSpent(4.99, 5), false);
  assert.equal(isSpent(100, 0), false, 'no cap is never spent');
  assert.equal(isNearly(4, 5), true);
  assert.equal(isNearly(5, 5), false);
  assert.equal(isNearly(3, 5), false);
});

test('what an admin types is the default when empty, a whole number of dollars up to 10000, or not valid', () => {
  assert.equal(parseCap(''), null);
  assert.equal(parseCap('  '), null);
  assert.equal(parseCap('0'), 0);
  assert.equal(parseCap(' 12 '), 12);
  assert.equal(parseCap('10000'), 10000);
  for (const bad of ['10001', '-1', '2,5', '1.5', 'abc', '99999']) assert.ok(Number.isNaN(parseCap(bad)), bad);
});

test('the line of a budget says what is spent of what and when it starts again, or that there is no limit', () => {
  assert.equal(budgetLine('Tu parte', { cap: null, spent: 3 }, '2026-12-01'), 'Tu parte: sin límite.');
  assert.equal(budgetLine('Tu parte', { cap: 0, spent: 0 }, '2026-12-01'), 'Tu parte: sin IA de la clave del grupo.');
  const line = budgetLine('Grupo', { cap: 20, spent: 1.5 }, '2026-12-01');
  assert.match(line, /^Grupo: 1,50.* de 20,00.*Se renueva el 1 de diciembre\.$/);
});
