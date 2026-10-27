import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ALL, money, monthChoices, monthLabel, selection, share } from '../js/lib/ai-usage.js';

const plain = (text) => text.replace(/\u00a0/g, ' '); // the locale puts a no-break space before the currency sign

const DATA = {
  currency: 'usd',
  total: 2.75,
  items: [{ name: 'a', amount: 2 }, { name: 'b', amount: 0.75 }],
  months: [
    { month: '2026-09', total: 1, items: [{ name: 'a', amount: 1 }] },
    { month: '2026-10', total: 1.75, items: [{ name: 'a', amount: 1 }, { name: 'b', amount: 0.75 }] },
  ],
  days: [{ date: '2026-09-30', total: 1 }, { date: '2026-10-01', total: 0.5 }, { date: '2026-10-02', total: 1.25 }],
};

test('an amount shows cents and keeps up to four decimals when it has them', () => {
  assert.match(plain(money(0.0123)), /^0,0123 US\$$/);
  assert.match(plain(money(12.5)), /^12,50 US\$$/);
  assert.match(plain(money(0)), /^0,00 US\$$/);
  assert.match(plain(money(0.6)), /^0,60 US\$$/);
  assert.match(plain(money(1.7123)), /^1,7123 US\$$/);
});

test('a month is named in Spanish with a capital', () => {
  assert.equal(monthLabel('2026-09'), 'Septiembre de 2026');
  assert.equal(monthLabel('2027-01'), 'Enero de 2027');
});

test('the months on offer are the ones with spend, the latest first', () => {
  assert.deepEqual(monthChoices(DATA), ['2026-10', '2026-09']);
  assert.deepEqual(DATA.months.map((m) => m.month), ['2026-09', '2026-10']); // the data is not reordered
});

test('everything is the total and no days; a month is its own figures and days', () => {
  assert.deepEqual(selection(DATA, ALL), { total: 2.75, items: DATA.items, days: [] });
  const october = selection(DATA, '2026-10');
  assert.equal(october.total, 1.75);
  assert.deepEqual(october.days.map((d) => d.date), ['2026-10-01', '2026-10-02']);
});

test('a month with no spend costs nothing', () => {
  assert.deepEqual(selection(DATA, '2026-01'), { total: 0, items: [], days: [] });
});

test('a bar is a percentage of the largest, and nothing to compare with is empty', () => {
  assert.equal(share(1, 4), 25);
  assert.equal(share(4, 4), 100);
  assert.equal(share(1, 0), 0);
});
