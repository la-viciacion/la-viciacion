import assert from 'node:assert/strict';
import { test } from 'node:test';
import { gap, isEmpty, parseAmount, realBalance, walletLine } from '../js/lib/ai-wallet.js';

test('an amount is dollars with up to two decimals, with a comma or a point, negative for a refund, never 0', () => {
  assert.equal(parseAmount('2'), 2);
  assert.equal(parseAmount(' 2,5 '), 2.5);
  assert.equal(parseAmount('2.50'), 2.5);
  assert.equal(parseAmount('-1,25'), -1.25);
  assert.equal(parseAmount('10000'), 10000);
  for (const bad of ['', '0', '0,00', 'abc', '2,555', '10001', '-10001', '1e3', '--2']) assert.ok(Number.isNaN(parseAmount(bad)), bad);
});

test('a balance of zero or less is nothing left', () => {
  assert.equal(isEmpty(0), true);
  assert.equal(isEmpty(-0.4), true);
  assert.equal(isEmpty(0.01), false);
});

test('the gap says how much more the OpenAI account holds than the wallets, rounded to the cent', () => {
  assert.equal(gap(12, 10.5), 1.5);
  assert.equal(gap(10, 10.5), -0.5);
  assert.equal(gap(0.3, 0.1 + 0.2), 0);
});

test('the player line says the balance, that it is spent or that there is no limit', () => {
  assert.equal(walletLine(null), '');
  assert.equal(walletLine({ contributed: 0, spent: 0, balance: 0, unlimited: true }), 'Tu saldo de IA del grupo: sin límite.');
  assert.match(walletLine({ contributed: 3, spent: 1, balance: 2 }), /Tu saldo de IA del grupo: 2,00.*aportado 3,00.*gastado 1,00/);
  assert.match(walletLine({ contributed: 1, spent: 1.4, balance: -0.4 }), /agotado.*Pide a un admin/);
});

test('the real balance adds what an admin typed for OpenAI to what the providers report, and is nothing without either', () => {
  assert.deepEqual(realBalance(NaN, []), { parts: [], sum: null });
  assert.deepEqual(realBalance(10, []), { parts: [{ name: 'OpenAI', amount: 10 }], sum: 10 });
  assert.equal(realBalance(NaN, [{ provider: 'openrouter', remaining: 4.5 }]).sum, 4.5);
  assert.deepEqual(realBalance(10.1, [{ provider: 'openrouter', remaining: 4.2 }, { provider: 'openrouter', error: 'x' }]).sum, 14.3);
  assert.equal(realBalance(0, []).sum, 0, 'a typed zero is a balance');
});
