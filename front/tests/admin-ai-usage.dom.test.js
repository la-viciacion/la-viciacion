import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { render } = await import('../js/pages/admin/ai-usage.js');

const plain = (text) => text.replace(/\s+/g, ' ');
const DATA = {
  configured: true,
  provider: 'openai',
  currency: 'usd',
  total: 3.25,
  items: [{ name: 'gpt-4.1-mini, output', amount: 1.5 }, { name: 'gpt-4.1-nano, input', amount: 1 }],
  months: [
    { month: '2026-09', total: 1, items: [{ name: 'gpt-4.1-nano, input', amount: 1 }] },
    { month: '2026-10', total: 2.25, items: [{ name: 'gpt-4.1-mini, output', amount: 1.5 }, { name: 'gpt-4.1-nano, input', amount: 0.75 }] },
  ],
  days: [{ date: '2026-09-30', total: 1 }, { date: '2026-10-01', total: 0.5 }, { date: '2026-10-02', total: 1.75 }],
};

const panel = () => document.getElementById('panel');
const rows = (section) => [...section.querySelectorAll('tbody tr')].map((tr) => [...tr.querySelectorAll('td')].map((td) => plain(td.textContent).trim()).filter(Boolean).join('|'));

test('without the admin key it says which variable is missing and asks nothing else', async () => {
  const calls = installApi({ 'GET /manage/ai-usage': { configured: false } });
  await render(panel());
  await settle();
  assert.match(panel().textContent, /Falta OPENAI_ADMIN_KEY en el \.env/);
  assert.equal(panel().querySelector('#aiuMonth'), null);
  assert.equal(calls.length, 1);
});

test('it opens on the whole year: the total and a row per month, the latest first', async () => {
  installApi({ 'GET /manage/ai-usage': DATA });
  await render(panel());
  await settle();
  const select = panel().querySelector('#aiuMonth');
  assert.deepEqual([...select.options].map((o) => o.value), ['all', '2026-10', '2026-09']);
  const [monthly, items] = panel().querySelectorAll('#aiuDetail .adm-set-card');
  assert.equal(rows(monthly).length, 2);
  assert.match(rows(monthly)[0], /^Octubre de 2026\|2,25/);
  assert.match(rows(monthly)[1], /^Septiembre de 2026\|1,00/);
  assert.match(rows(items)[0], /^gpt-4\.1-mini, output\|1,50/);
  assert.match(panel().querySelector('#aiuDetail .adm-stat-v').textContent, /3,25/);
  assert.deepEqual([...panel().querySelectorAll('#aiuDetail h3')].map((h) => h.textContent), ['Por mes', 'Por concepto']);
});

test('choosing a month shows its items and its days without asking the API again', async () => {
  const calls = installApi({ 'GET /manage/ai-usage': DATA });
  await render(panel());
  await settle();
  const select = panel().querySelector('#aiuMonth');
  select.value = '2026-10';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  const sections = [...panel().querySelectorAll('#aiuDetail .adm-set-card')];
  assert.equal(sections.length, 2);
  assert.deepEqual(rows(sections[0]).map((r) => r.split('|')[0]), ['gpt-4.1-mini, output', 'gpt-4.1-nano, input']);
  assert.deepEqual(rows(sections[1]).map((r) => r.split('|')[0]), ['2026-10-01', '2026-10-02']);
  assert.match(panel().querySelector('#aiuDetail .adm-stat-v').textContent, /2,25/);
  assert.equal(calls.length, 1);
});

test('Actualizar asks the API to ask OpenAI again and keeps the month if it still exists', async () => {
  const calls = installApi({ 'GET /manage/ai-usage': DATA });
  await render(panel());
  await settle();
  panel().querySelector('#aiuRefresh').click();
  await settle();
  assert.equal(calls.at(-1).path, '/manage/ai-usage?refresh=true');
});

test('a failure of OpenAI is shown as the error', async () => {
  installApi({ 'GET /manage/ai-usage': json({ detail: 'OpenAI rechaza la clave de administración' }, 502) });
  await render(panel());
  await settle();
  assert.match(panel().textContent, /OpenAI rechaza la clave/);
});
