import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { renderBudgets } = await import('../js/pages/admin/ai-budgets.js');

const panel = () => document.getElementById('panel');
const DATA = {
  month: '2026-11',
  resets_on: '2026-12-01',
  group: { cap: 20, spent: 17 },
  default_user_cap: 5,
  players: [
    { user_id: 1, name: 'Ana', is_active: true, override: null, cap: 5, spent: 5.5, calls: 12 },
    { user_id: 2, name: 'Beto', is_active: true, override: 9, cap: 9, spent: 1, calls: 3 },
    { user_id: 4, name: 'Cris', is_active: false, override: null, cap: 5, spent: 0, calls: 0 },
  ],
};
const open = async (data = DATA) => {
  panel().replaceWith(panel().cloneNode(false));
  const log = installApi({ 'GET /manage/ai-usage/budgets': data });
  await renderBudgets(panel());
  await settle();
  return log;
};
const row = (id) => panel().querySelector(`tr[data-user="${id}"]`);

test('it shows what the group has spent of its budget, when it starts again and each player with their cap and what they spent', async () => {
  await open();
  const text = panel().textContent;
  assert.match(text, /Gastado este mes de 20,00/);
  assert.match(text, /Se renueva el 1 de diciembre/);
  assert.deepEqual([...panel().querySelectorAll('tbody tr')].map((r) => r.querySelector('td').textContent.trim().replace(/\s+/g, ' ')), ['Ana', 'Beto', 'Cris Inactivo']);
  assert.match(row(1).textContent, /12/);
  assert.match(row(1).textContent, /Agotado/, 'Ana has spent more than her 5');
  assert.doesNotMatch(row(2).textContent, /Agotado|Casi/);
});

test('a player with an individual cap shows it in the box, and one with the default shows it as the hint', async () => {
  await open();
  assert.equal(row(2).querySelector('[name="cap"]').value, '9');
  assert.equal(row(1).querySelector('[name="cap"]').value, '');
  assert.match(row(1).querySelector('[name="cap"]').placeholder, /5,00/);
});

test('without a group cap it says there is no limit instead of a bar', async () => {
  await open({ ...DATA, group: { cap: 0, spent: 3 } });
  assert.match(panel().textContent, /El grupo no tiene tope/);
});

test('saving sends the whole dollars and draws the table again', async () => {
  const log = await open();
  row(1).querySelector('[name="cap"]').value = ' 12 ';
  installApi({
    'PUT /manage/ai-usage/budgets/1': ({ body }) => { assert.deepEqual(body, { usd: 12 }); return { ...DATA.players[0], override: 12, cap: 12 }; },
    'GET /manage/ai-usage/budgets': { ...DATA, players: [{ ...DATA.players[0], override: 12, cap: 12 }, ...DATA.players.slice(1)] },
  });
  row(1).querySelector('[data-save]').click();
  await settle();
  await settle();
  assert.equal(row(1).querySelector('[name="cap"]').value, '12');
  assert.ok(log.length >= 1);
});

test('an empty box sends null, which goes back to the default, and a zero is a real value', async () => {
  await open();
  const sent = [];
  installApi({
    'PUT /manage/ai-usage/budgets/2': ({ body }) => { sent.push(body); return {}; },
    'GET /manage/ai-usage/budgets': DATA,
  });
  row(2).querySelector('[name="cap"]').value = '';
  row(2).querySelector('[data-save]').click();
  await settle();
  await settle();
  row(2).querySelector('[name="cap"]').value = '0';
  row(2).querySelector('[data-save]').click();
  await settle();
  await settle();
  assert.deepEqual(sent, [{ usd: null }, { usd: 0 }]);
});

test('a number that is not whole dollars is not even sent', async () => {
  const log = await open();
  row(1).querySelector('[name="cap"]').value = '2,5';
  row(1).querySelector('[data-save]').click();
  await settle();
  assert.equal(log.filter((c) => c.method === 'PUT').length, 0);
});

test('a failure shows as the error and leaves nothing half drawn', async () => {
  installApi({ 'GET /manage/ai-usage/budgets': () => json({ detail: 'sin base de datos' }, 500) });
  panel().replaceWith(panel().cloneNode(false));
  await renderBudgets(panel());
  assert.match(panel().textContent, /sin base de datos/);
});

test('calls of a model with no price are warned about, because no budget can limit them', async () => {
  await open({ ...DATA, unpriced: { calls: 3, models: ['openai/gpt-9-new'] } });
  const warn = panel().querySelector('.adm-warn').textContent;
  assert.match(warn, /3 llamadas/);
  assert.match(warn, /openai\/gpt-9-new/);
  assert.match(warn, /no se pueden limitar/);
});

test('with none, or with no budget at all, there is nothing to warn about', async () => {
  await open({ ...DATA, unpriced: { calls: 0, models: [] } });
  assert.equal(panel().querySelector('.adm-warn'), null);
  await open({ ...DATA, group: { cap: 0, spent: 0 }, default_user_cap: 0, players: [], unpriced: { calls: 2, models: ['openai/x'] } });
  assert.equal(panel().querySelector('.adm-warn'), null);
});
