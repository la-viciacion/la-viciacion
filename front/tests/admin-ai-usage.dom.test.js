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
const asked = (calls) => calls.filter((c) => !c.path.includes('/calls') && !c.path.includes('/settings') && !c.path.includes('provider=')); // what was asked of OpenAI's side, not of the app's record, of Anthropic's block or of the settings below it
const rows = (section) => [...section.querySelectorAll('tbody tr')].map((tr) => [...tr.querySelectorAll('td')].map((td) => plain(td.textContent).trim()).filter(Boolean).join('|'));

test('without the admin key it says which variable is missing and asks nothing else', async () => {
  const calls = installApi({ 'GET /manage/ai-usage': { configured: false } });
  await render(panel());
  await settle();
  assert.match(panel().textContent, /Falta OPENAI_ADMIN_KEY en el \.env/);
  assert.equal(panel().querySelector('#aiuMonth-openai'), null);
  assert.equal(asked(calls).length, 1);
});

test('it opens on the whole year: the total and a row per month, the latest first', async () => {
  installApi({ 'GET /manage/ai-usage': DATA });
  await render(panel());
  await settle();
  const select = panel().querySelector('#aiuMonth-openai');
  assert.deepEqual([...select.options].map((o) => o.value), ['all', '2026-10', '2026-09']);
  const [monthly, items] = panel().querySelectorAll('#aiuDetail-openai .adm-set-card');
  assert.equal(rows(monthly).length, 2);
  assert.match(rows(monthly)[0], /^Octubre de 2026\|2,25/);
  assert.match(rows(monthly)[1], /^Septiembre de 2026\|1,00/);
  assert.match(rows(items)[0], /^gpt-4\.1-mini, output\|1,50/);
  assert.match(panel().querySelector('#aiuDetail-openai .adm-stat-v').textContent, /3,25/);
  assert.deepEqual([...panel().querySelectorAll('#aiuDetail-openai h3')].map((h) => h.textContent), ['Por mes', 'Por concepto']);
});

test('choosing a month shows its items and its days without asking the API again', async () => {
  const calls = installApi({ 'GET /manage/ai-usage': DATA });
  await render(panel());
  await settle();
  const select = panel().querySelector('#aiuMonth-openai');
  select.value = '2026-10';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  const sections = [...panel().querySelectorAll('#aiuDetail-openai .adm-set-card')];
  assert.equal(sections.length, 2);
  assert.deepEqual(rows(sections[0]).map((r) => r.split('|')[0]), ['gpt-4.1-mini, output', 'gpt-4.1-nano, input']);
  assert.deepEqual(rows(sections[1]).map((r) => r.split('|')[0]), ['2026-10-01', '2026-10-02']);
  assert.match(panel().querySelector('#aiuDetail-openai .adm-stat-v').textContent, /2,25/);
  assert.equal(asked(calls).length, 1);
});

test('Actualizar asks the API to ask OpenAI again and keeps the month if it still exists', async () => {
  const calls = installApi({ 'GET /manage/ai-usage': DATA });
  await render(panel());
  await settle();
  panel().querySelector('#aiuRefresh-openai').click();
  await settle();
  assert.equal(asked(calls).at(-1).path, '/manage/ai-usage?refresh=true');
});

test('each month sets what OpenAI billed against what the app estimates, and says what is left unexplained', async () => {
  installApi({
    'GET /manage/ai-usage/calls': { ...CALLS, months: [{ month: '2026-10', calls: 3, cost: 2, group_cost: 2, group_real_cost_by_provider: { openai: 2 }, user_cost: 0, unpriced: 0 }] },
    'GET /manage/ai-usage': DATA,
  });
  await render(panel());
  await settle();
  const [monthly] = panel().querySelectorAll('#aiuDetail-openai .adm-set-card');
  assert.match(rows(monthly)[0], /^Octubre de 2026\|2,25[^|]*\|2,00[^|]*\|0,25/);
  assert.match(rows(monthly)[1], /^Septiembre de 2026\|1,00[^|]*\|0,00[^|]*\|1,00/);
  const select = panel().querySelector('#aiuMonth-openai');
  select.value = '2026-10';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  const tiles = [...panel().querySelectorAll('#aiuDetail-openai .adm-stat')].map((t) => plain(t.textContent));
  assert.ok(tiles.some((t) => /2,00.*Estimado por la app/.test(t)), tiles.join(' / '));
  assert.ok(tiles.some((t) => /0,25.*Sin explicar/.test(t)), tiles.join(' / '));
});

test('a failure of OpenAI is shown as the error', async () => {
  installApi({ 'GET /manage/ai-usage': json({ detail: 'OpenAI rechaza la clave de administración' }, 502) });
  await render(panel());
  await settle();
  assert.match(panel().textContent, /OpenAI rechaza la clave/);
});

const figures = (calls, cost, extra = {}) => ({ calls, cost, input_tokens: 1200, cached_tokens: 0, output_tokens: 300, web_searches: 0, unpriced: 0, ...extra });
const CALLS = {
  total: figures(4, 0.75),
  by_source: [{ name: 'group', ...figures(3, 0.5) }, { name: 'user', ...figures(1, 0.25) }],
  by_feature: [{ name: 'guide', ...figures(1, 0.6, { web_searches: 2 }) }, { name: 'chat', ...figures(3, 0.15) }],
  by_model: [{ name: 'openai/gpt-4.1-mini', ...figures(4, 0.75) }],
  by_tools: [{ name: 'web_search', ...figures(1, 0.6) }, { name: 'ranking', ...figures(2, 0.1) }, { name: 'Sin herramientas', ...figures(1, 0.05) }],
  by_status: [{ name: 'ok', calls: 3 }, { name: 'off_topic', calls: 1 }],
  group_paid_by_user: [{ user_id: 1, name: 'Ana', ...figures(2, 0.4) }, { user_id: 2, name: 'Beto', ...figures(1, 0.1) }],
  months: [{ month: '2026-11', calls: 4, cost: 0.75, group_cost: 0.5, user_cost: 0.25, unpriced: 0 }],
  days: [],
  price_stamp: '2026-11-12T10:25:43',
  retention_days: 0,
  price_refresh_hours: 24,
  price_updates_running: true,
};
const open = async (calls = CALLS) => {
  const log = installApi({ 'GET /manage/ai-usage/calls': calls, 'GET /manage/ai-usage/wallet': { active: false, start: null, start_setting: null, total: { contributed: 0, spent: 0, available: 0 }, players: [], entries: [] }, 'GET /manage/ai-usage/budgets': { month: '2026-11', resets_on: '2026-12-01', group: { cap: 0, spent: 0 }, default_user_cap: 0, players: [] }, 'GET /manage/ai-usage': { configured: false } }); // the longer path first: a route matches by its start
  await render(panel());
  await settle();
  return log;
};
const section = (name) => panel().querySelector(`.adm-calls-${name}`);

test('the app record comes first and needs no OpenAI key: who paid, by player, by function and by kind of question', async () => {
  await open();
  assert.match(panel().querySelector('.adm-calls-head').textContent, /estimación/);
  assert.match(panel().querySelector('.adm-calls-head').textContent, /2026-11-12/);
  assert.match(panel().querySelector('.adm-calls-head').textContent, /Los límites y el presupuesto se gestionan en IA → Límites/);
  assert.deepEqual(rows(section('source')).map((r) => r.split('|')[0]), ['Clave del grupo', 'Clave propia de cada jugador']);
  assert.deepEqual(rows(section('players')).map((r) => r.split('|')[0]), ['Ana', 'Beto']);
  assert.deepEqual(rows(section('feature')).map((r) => r.split('|')[0]), ['Guía de juego', 'Chat']);
  assert.deepEqual(rows(section('tools')).map((r) => r.split('|')[0]), ['web_search', 'ranking', 'Sin herramientas']);
  assert.match(panel().textContent, /Falta OPENAI_ADMIN_KEY/); // OpenAI's part is still there, apart
});

test('when some calls went to Google the panel says its figure is only an estimate', async () => {
  await open({ ...CALLS, by_model: [{ name: 'openai/gpt-4.1-mini', ...figures(3, 0.7) }, { name: 'google/gemini-2.5-flash', ...figures(1, 0.05) }] });
  assert.match(panel().querySelector('.adm-calls-google').textContent, /solo una estimación/);
  await open();
  assert.equal(panel().querySelector('.adm-calls-google'), null);
});

test('calls on a free plan show the real cost beside the estimate, and say they cost nothing', async () => {
  await open({ ...CALLS, total: figures(4, 0.75, { real_cost: 0.5, free_calls: 2 }) });
  const tiles = [...panel().querySelectorAll('.adm-calls-head ~ #aicDetail .adm-stat, #aicDetail .adm-stat')].map((t) => plain(t.textContent));
  assert.ok(tiles.some((t) => /0,50.*Coste real/.test(t)), tiles.join(' / '));
  assert.match(panel().querySelector('.adm-calls-free').textContent, /2 llamadas con una clave de plan gratuito.*0 US\$/);
  await open();
  assert.equal(panel().querySelector('.adm-calls-free'), null);
});

test('a player who paid with their own key is never named: only the totals of that source', async () => {
  await open();
  assert.doesNotMatch(section('source').textContent, /Ana|Beto/);
  assert.match(section('players').textContent, /no se detalla por nombre/);
});

test('calls with no known price are said so and do not count as free', async () => {
  await open({ ...CALLS, total: figures(4, 0.75, { unpriced: 2 }), by_model: [{ name: 'openai/mystery', ...figures(2, 0, { unpriced: 2 }) }] });
  assert.match(panel().querySelector('.adm-warn').textContent, /2 llamadas sin precio conocido/);
  assert.match(rows(section('model'))[0], /sin precio/);
});

test('choosing a month asks the API for that month and shows its days instead of the months', async () => {
  const log = await open();
  const select = panel().querySelector('#aicMonth');
  select.value = '2026-11';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  assert.equal(log.at(-1).path, '/manage/ai-usage/calls?month=2026-11');
});

test('an empty record says so instead of showing empty tables', async () => {
  await open({ ...CALLS, total: figures(0, 0), by_source: [], by_feature: [], by_model: [], by_tools: [], by_status: [], group_paid_by_user: [], months: [] });
  assert.match(section('players').textContent, /Todavía nadie ha usado la clave del grupo/);
  assert.match(section('months').textContent, /Sin llamadas/);
});

test('a failure of the record is shown without hiding what OpenAI billed', async () => {
  installApi({ 'GET /manage/ai-usage/calls': json({ detail: 'sin base de datos' }, 500), 'GET /manage/ai-usage': DATA });
  await render(panel());
  await settle();
  assert.match(panel().querySelector('#aicApp').textContent, /sin base de datos/);
  assert.ok(panel().querySelector('#aiuMonth-openai'));
});

const SETTINGS = {
  values: { 'ai.price_refresh_hours': 24, 'ai.usage_retention_days': 90, 'telegram.token': { is_set: false }, 'telegram.group_id': { is_set: false }, 'telegram.admin_chat_id': { is_set: false }, 'ai.openai.api_key': { is_set: false }, 'ai.openai_admin_key': { is_set: false }, 'ai.anthropic_admin_key': { is_set: false }, 'push.vapid_private': { is_set: false } },
  jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: [], ai_model: { provider: 'google', model: 'm' }, chat: {}, guide: {},
};

test('how the cost is worked out and how long the record is kept are settings of this same page, below what it shows, with their own Guardar', async () => {
  let saved = null;
  installApi({
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: Object.keys(body.values), values: SETTINGS.values }; },
    'GET /manage/settings': SETTINGS,
    'GET /manage/ai-usage/calls': CALLS,
    'GET /manage/ai-usage': { configured: false },
  });
  panel().replaceWith(panel().cloneNode(false));
  await render(panel());
  await settle();
  await settle();
  const card = panel().querySelector('#aicSettings .adm-aicost-card');
  assert.equal(card.querySelector('h3').textContent, 'Coste de la IA');
  assert.deepEqual([...card.querySelectorAll('input[type="number"]')].map((i) => [i.name, i.value]), [['ai.price_refresh_hours', '24'], ['ai.usage_retention_days', '90']]);
  const order = [...panel().children].map((c) => c.id);
  assert.deepEqual(order, ['aicApp', 'aiuBilled-openai', 'aiuBilled-anthropic', 'aicSettings'], 'the record, what each provider billed, then the settings');
  card.querySelector('input[name="ai.usage_retention_days"]').value = '30';
  panel().querySelector('#admSettings').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(saved.values, { 'ai.usage_retention_days': 30 });
});

// ---- Anthropic: the same block, for the provider that bills by its own admin key
const ANTHROPIC = {
  ...DATA,
  provider: 'anthropic',
  total: 4.5,
  items: [{ name: 'Claude Haiku 5.5 Usage - Output Tokens', amount: 3 }, { name: 'Web Search Usage', amount: 1.5 }],
  months: [{ month: '2026-10', total: 4.5, items: [{ name: 'Claude Haiku 5.5 Usage - Output Tokens', amount: 3 }, { name: 'Web Search Usage', amount: 1.5 }] }],
  days: [{ date: '2026-10-01', total: 4.5 }],
};
const anthropicBlock = () => panel().querySelector('#aiuBilled-anthropic');
const openBoth = async (extra = {}) => {
  panel().replaceWith(panel().cloneNode(false));
  const own = 'GET /manage/ai-usage?provider=anthropic';
  // a route matches by its start: the longer paths (the record, Anthropic's) go before OpenAI's
  const log = installApi({ ...extra, [own]: extra[own] ?? { configured: false, provider: 'anthropic', provider_key: false }, 'GET /manage/ai-usage': DATA });
  await render(panel());
  await settle();
  return log;
};

test('without an Anthropic key nothing is said about Anthropic, and OpenAI keeps its block', async () => {
  await openBoth();
  assert.equal(anthropicBlock().textContent.trim(), '');
  assert.ok(panel().querySelector('#aiuMonth-openai'));
});

test('with a key of Anthropic to write text but no admin key it says which variable is missing and that an organization is needed', async () => {
  await openBoth({ 'GET /manage/ai-usage?provider=anthropic': { configured: false, provider: 'anthropic', provider_key: true } });
  assert.match(anthropicBlock().textContent, /Falta ANTHROPIC_ADMIN_KEY en el \.env/);
  assert.match(anthropicBlock().textContent, /organización/);
  assert.equal(anthropicBlock().querySelector('#aiuMonth-anthropic'), null);
});

test('with its admin key Anthropic gets its own block, asked with its provider and apart from OpenAI', async () => {
  const log = await openBoth({ 'GET /manage/ai-usage?provider=anthropic': ANTHROPIC });
  assert.match(anthropicBlock().textContent, /Gasto en Anthropic/);
  assert.match(anthropicBlock().querySelector('.adm-stat-v').textContent, /4,50/);
  assert.match(rows(anthropicBlock().querySelectorAll('#aiuDetail-anthropic .adm-set-card')[1])[0], /^Claude Haiku 5\.5 Usage - Output Tokens\|3,00/);
  assert.match(panel().querySelector('#aiuBilled-openai').querySelector('.adm-stat-v').textContent, /3,25/, 'OpenAI keeps its own figures');
  assert.ok(log.some((c) => c.path.includes('provider=anthropic')));
});

test('Anthropic is set against what the app estimates for Anthropic, not for OpenAI', async () => {
  await openBoth({
    'GET /manage/ai-usage?provider=anthropic': ANTHROPIC,
    'GET /manage/ai-usage/calls': { ...CALLS, months: [{ month: '2026-10', calls: 3, cost: 2, group_cost: 2, group_real_cost_by_provider: { openai: 2, anthropic: 4 }, user_cost: 0, unpriced: 0 }] },
  });
  const monthly = anthropicBlock().querySelector('#aiuDetail-anthropic .adm-set-card');
  assert.match(rows(monthly)[0], /^Octubre de 2026\|4,50.*\|4,00.*\|0,50/, 'billed 4.50, estimated 4.00 of Anthropic, 0.50 unexplained');
});

test('Actualizar of Anthropic asks for fresh data of Anthropic only', async () => {
  const log = await openBoth({ 'GET /manage/ai-usage?provider=anthropic': ANTHROPIC });
  const before = log.length;
  anthropicBlock().querySelector('#aiuRefresh-anthropic').click();
  await settle();
  const fresh = log.slice(before).filter((c) => c.path.includes('refresh=true'));
  assert.equal(fresh.length, 1);
  assert.match(fresh[0].path, /provider=anthropic.*refresh=true|refresh=true.*provider=anthropic/);
});

test('a failure of Anthropic is shown in its block and OpenAI is untouched', async () => {
  await openBoth({ 'GET /manage/ai-usage?provider=anthropic': json({ detail: 'Anthropic rechaza la clave de administración' }, 502) });
  assert.match(anthropicBlock().textContent, /Anthropic rechaza la clave de administración/);
  assert.ok(panel().querySelector('#aiuMonth-openai'));
});
