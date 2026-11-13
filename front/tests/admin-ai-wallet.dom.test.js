import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { renderWallet } = await import('../js/pages/admin/ai-wallet.js');

const panel = () => document.getElementById('panel');
const DATA = {
  active: true,
  start: '2026-11-10',
  start_setting: null,
  total: { contributed: 6, spent: 2.5, available: 3.5 },
  players: [
    { user_id: 1, name: 'Ana', is_active: true, contributed: 4, spent: 4.4, balance: -0.4 },
    { user_id: 2, name: 'Beto', is_active: true, contributed: 2, spent: 0, balance: 2 },
  ],
  entries: [{ id: 2, created_at: '2026-11-11T10:00:00', user_id: 2, name: 'Beto', usd: 2, note: 'bizum', by: 'Ana' }],
};
const open = async (data = DATA, extra = {}) => {
  panel().replaceWith(panel().cloneNode(false));
  const log = installApi({ 'GET /manage/ai-usage/wallet': data, ...extra });
  await renderWallet(panel());
  await settle();
  return log;
};
const field = (name) => panel().querySelector(`[data-field="${name}"]`);

test('it shows what is in, what is spent and what is available, and who has nothing left', async () => {
  await open();
  const text = panel().textContent;
  assert.match(text, /Aportado/);
  assert.match(text, /3,50/);
  const ana = panel().querySelector('tr[data-user="1"]');
  assert.match(ana.textContent, /En negativo/);
  assert.doesNotMatch(panel().querySelector('tr[data-user="2"]').textContent, /Sin saldo|negativo/);
});

test('with the wallet off it says so', async () => {
  await open({ ...DATA, active: false, start: null, total: { contributed: 0, spent: 0, available: 0 }, entries: [] });
  assert.match(panel().textContent, /apagado/);
});

test('it compares the OpenAI balance typed with the total available', async () => {
  await open();
  field('openai').value = '5';
  field('openai').dispatchEvent(new window.Event('input', { bubbles: true }));
  assert.match(panel().querySelector('[data-compare]').textContent, /más de lo que dice el monedero/);
  field('openai').value = '3,5';
  field('openai').dispatchEvent(new window.Event('input', { bubbles: true }));
  assert.match(panel().querySelector('[data-compare]').textContent, /Cuadra/);
});

test('writing down a contribution posts it and draws the answer', async () => {
  const log = await open(DATA, { 'POST /manage/ai-usage/wallet/entries': { ...DATA, total: { contributed: 8.5, spent: 2.5, available: 6 } } });
  field('user').value = '2';
  field('amount').value = '2,50';
  field('note').value = 'bizum';
  panel().querySelector('[data-add]').click();
  await settle();
  const sent = log.find((c) => c.method === 'POST');
  assert.deepEqual(sent.body, { user_id: 2, usd: 2.5, note: 'bizum' });
  assert.match(panel().textContent, /6,00/);
});

test('an amount that is not valid is not sent', async () => {
  const log = await open();
  field('amount').value = 'abc';
  panel().querySelector('[data-add]').click();
  await settle();
  assert.equal(log.some((c) => c.method === 'POST'), false);
});

test('the start date is saved, and empty goes back to the first contribution', async () => {
  const log = await open(DATA, { 'PUT /manage/ai-usage/wallet/start': { ...DATA, start_setting: '2026-11-01', start: '2026-11-01' } });
  field('start').value = '2026-11-01';
  panel().querySelector('[data-save-start]').click();
  await settle();
  assert.deepEqual(log.find((c) => c.method === 'PUT').body, { date: '2026-11-01' });
});

test('a failure shows only in the card', async () => {
  panel().replaceWith(panel().cloneNode(false));
  installApi({ 'GET /manage/ai-usage/wallet': json({ detail: 'boom' }, 500) });
  await renderWallet(panel());
  await settle();
  assert.match(panel().textContent, /boom/);
});
