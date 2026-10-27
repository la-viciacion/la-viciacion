import assert from 'node:assert/strict';
import { test } from 'node:test';
import { euros, paidText, parseEuros, perHour } from '../js/lib/money.js';

const plain = (text) => text.replace(/\u00a0/g, ' '); // the locale puts a no-break space before the euro sign

test('cents are euros, whole ones without decimals', () => {
  assert.equal(plain(euros(2999)), '29,99 €');
  assert.equal(plain(euros(1000)), '10 €');
  assert.equal(plain(euros(5)), '0,05 €');
  assert.equal(plain(euros(0)), '0 €');
});

test('a price typed with a comma or a point is a number, an empty box is none and nonsense is NaN', () => {
  assert.equal(parseEuros('29,99'), 29.99);
  assert.equal(parseEuros(' 29.99 '), 29.99);
  assert.equal(parseEuros('10'), 10);
  assert.equal(parseEuros(''), null);
  assert.equal(parseEuros(null), null);
  for (const bad of ['abc', '-5', '1,234', '1.2.3', '10 €']) assert.ok(Number.isNaN(parseEuros(bad)), bad);
});

test('a row says what was paid in total over its platforms, or nothing', () => {
  assert.equal(plain(paidText([{ id: 'pc', price_cents: 1999 }, { id: 'switch', price_cents: 4000 }, { id: 'ps5', price_cents: null }])), '59,99 €');
  assert.equal(paidText([{ id: 'pc', price_cents: null }]), '');
  assert.equal(paidText(undefined), '');
  assert.equal(plain(paidText([{ id: 'pc', price_cents: 0 }])), '0 €'); // a free game is a price
});

test('a cost per hour has two decimals', () => {
  assert.equal(plain(perHour(250)), '2,50 €/h');
  assert.equal(plain(perHour(1)), '0,01 €/h');
});
