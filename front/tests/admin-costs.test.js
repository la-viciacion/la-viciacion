import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ENTITIES } from '../js/pages/admin/entities.js';
import { TAB_IDS } from '../js/pages/admin/nav.js';

const costs = ENTITIES.costs;
const row = { id: 1, name: 'Dominio <b>', kind: 'domain', amount: 12, period: 'year', starts_on: '2026-01-01', ends_on: null, source: 'manual', note: '.com' };
const cell = (label, r = row) => String(costs.columns.find((c) => c.label === label).render(r));

test('the costs are a tab of the panel and a plain list of rates', () => {
  assert.ok(TAB_IDS.includes('costs'));
  assert.equal(costs.endpoint, '/manage/costs');
  assert.equal(costs.paged, false);
  assert.equal(costs.canDelete, true);
});

test('a rate reads as its concept, its amount per period and the days it applies', () => {
  assert.match(cell('Concepto'), /Dominio &lt;b&gt;/); // escaped
  assert.match(cell('Concepto'), /Dominio · \.com/);
  assert.match(cell('Importe').replace(/\s/g, ' '), /^12 € al año$/);
  assert.match(cell('Hasta'), /Vigente/);
  assert.doesNotMatch(cell('Hasta', { ...row, ends_on: '2026-06-30' }), /Vigente/);
  assert.equal(cell('Hasta', { ...row, period: 'once' }), '—'); // a one-off cost has a day and no end
});

test('what comes from Hetzner is marked, and the euros take cents', () => {
  assert.match(cell('Concepto', { ...row, kind: 'server', source: 'hetzner', note: null }), /Servidor · desde Hetzner/);
  assert.match(cell('Importe', { ...row, amount: 5.43, period: 'month' }).replace(/\s/g, ' '), /^5,43 € al mes$/);
});

test('the form asks for euros with cents and offers the kinds and periods the API accepts', () => {
  const field = (key) => costs.fields.find((f) => f.key === key);
  assert.equal(field('amount').step, '0.01');
  assert.deepEqual(field('kind').options.map(([value]) => value), ['server', 'domain', 'other']);
  assert.deepEqual(field('period').options.map(([value]) => value), ['month', 'year', 'once']);
  assert.deepEqual(costs.createFields.map((f) => f.key), costs.fields.map((f) => f.key));
});
