import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
const window = installDom('<div id="pfAi"></div>', 'http://localhost/');
globalThis.location = window.location;
const { initAi } = await import('../js/pages/profile/ai.js');

const KEY = 'sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789';
const NONE = { has_key: false, unreadable: false, hint: null, model: null, provider: 'openai' };
const OWN = { has_key: true, unreadable: false, hint: '6789', model: 'gpt-4.1-mini', provider: 'openai' };
const stateOf = (key) => ({
  key,
  chat: { available: true, needs_key: false, paid_by: 'group', mode: 'group_then_user', blocked: null }, // the group's first, with a key or not
  guide: { available: true, needs_key: !key.has_key, paid_by: key.has_key ? 'user' : null, mode: 'user_only' },
  default_model: 'gpt-4.1-mini',
});
const MODELS = {
  models: [
    { id: 'gpt-4.1-mini', tier: 'economico', input_per_million: 0.4, output_per_million: 1.6 },
    { id: 'gpt-5', tier: 'medio', input_per_million: 1.25, output_per_million: 10 },
  ],
  current: 'gpt-4.1-mini',
};

const figures = (calls, cost, extra = {}) => ({ calls, cost, input_tokens: 1000, cached_tokens: 0, output_tokens: 200, web_searches: 0, unpriced: 0, ...extra });
const NOTHING = {
  total: figures(0, 0), by_source: [], by_feature: [], by_model: [], by_status: [], months: [], days: [],
  budget: { month: '2026-11', resets_on: '2026-12-01', group: { cap: 0, spent: 0 }, user: { cap: 0, spent: 0 } },
};
const el = () => document.getElementById('pfAi');
const open = async (routes) => {
  el().replaceWith(el().cloneNode(false)); // a new element: the listeners of the screen before it go with the old one
  // the longer path first: a route matches by its start
  const calls = installApi({ 'GET /users/ana/ai/usage': NOTHING, ...routes });
  await initAi(el(), { username: 'ana' });
  await settle();
  return calls;
};
const submitKey = async (value) => {
  el().querySelector('[name="api_key"]').value = value;
  el().querySelector('[data-form="key"]').requestSubmit();
  await settle();
  await settle();
};
const sent = (calls, method) => calls.filter((c) => c.method === method).map((c) => c.body);

beforeEach(() => el().replaceWith(el().cloneNode(false)));

test('without a key it says, quietly, where the cost goes, offers the key box and loads no models', async () => {
  const calls = await open({ 'GET /users/ana/ai': stateOf(NONE) });
  const note = el().querySelector('.ai-cost-note').textContent;
  assert.match(note, /El coste del chat lo cubre el grupo mientras haya presupuesto este mes; después necesitarás tu propia clave/);
  assert.match(note, /La guía de cada juego busca en internet y cuesta más: funciona con tu propia clave/);
  assert.equal([...el().querySelectorAll('h2')].some((h) => /Quién paga/.test(h.textContent)), false, 'no section of its own');
  assert.equal(el().querySelector('input[type="password"]').name, 'api_key');
  assert.equal(el().querySelector('select[name="model"]'), null);
  assert.equal(calls.some((c) => c.path.endsWith('/models')), false);
});

test('what is typed that does not look like a key is not even sent', async () => {
  const calls = await open({ 'GET /users/ana/ai': stateOf(NONE) });
  await submitKey('hola');
  assert.match(el().querySelector('[data-msg="key"]').textContent, /empieza por sk-/);
  assert.deepEqual(sent(calls, 'PUT'), []);
});

test('a key is saved, then only its last characters and its model show, and the models of the account are offered', async () => {
  let saved = false;
  const calls = await open({
    'PUT /users/ana/ai': () => { saved = true; return OWN; },
    'GET /users/ana/ai/models': MODELS,
    'GET /users/ana/ai': () => json(stateOf(saved ? OWN : NONE)),
  });
  await submitKey(` ${KEY} `);
  assert.deepEqual(sent(calls, 'PUT'), [{ api_key: KEY }]);
  assert.match(el().textContent, /Clave guardada, termina en …6789/);
  const kept = el().querySelector('.ai-cost-note').textContent;
  assert.match(kept, /El coste del chat lo cubre el grupo mientras haya presupuesto este mes; después seguirá con tu clave/);
  assert.match(kept, /El coste de la guía va a tu cuenta de OpenAI/);
  assert.equal(el().textContent.includes(KEY), false, 'the key is never drawn');
  assert.equal(el().querySelector('input[type="password"]'), null, 'the box goes away once it is saved');
  const options = [...el().querySelectorAll('select[name="model"] option')];
  assert.deepEqual(options.map((o) => o.value), ['gpt-4.1-mini', 'gpt-5']);
  assert.match(options[1].textContent, /gpt-5 · precio medio · 1,25.*10,00/);
  assert.equal(options[0].selected, true);
});

test('a key that OpenAI refuses shows the reason and leaves the box empty, never repeating the key', async () => {
  await open({
    'PUT /users/ana/ai': () => json({ detail: 'OpenAI no acepta esa clave.' }, 400),
    'GET /users/ana/ai': stateOf(NONE),
  });
  await submitKey(KEY);
  assert.match(el().querySelector('[data-msg="key"]').textContent, /OpenAI no acepta esa clave/);
  assert.equal(el().querySelector('[name="api_key"]').value, '');
  assert.equal(el().textContent.includes(KEY), false);
});

test('choosing another model sends only the model', async () => {
  const calls = await open({
    'PUT /users/ana/ai': ({ body }) => ({ ...OWN, model: body.model }),
    'GET /users/ana/ai/models': MODELS,
    'GET /users/ana/ai': stateOf(OWN),
  });
  const select = el().querySelector('select[name="model"]');
  select.value = 'gpt-5';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  await settle();
  assert.deepEqual(sent(calls, 'PUT'), [{ model: 'gpt-5' }]);
  assert.match(el().querySelector('[data-msg="model"]').textContent, /Modelo guardado: gpt-5/);
});

test('a model that is not in the list of the account is still shown, as the one they have', async () => {
  await open({ 'GET /users/ana/ai/models': MODELS, 'GET /users/ana/ai': stateOf({ ...OWN, model: 'my-custom-model' }) }); // the longer path first: a route matches by its start
  assert.equal(el().querySelector('select[name="model"]').value, 'my-custom-model');
});

test('the test says it spends a little, and shows the answer or the error', async () => {
  const log = await open({
    'POST /users/ana/ai/test': { reply: 'Team Cherry', model: 'gpt-4.1-mini' },
    'GET /users/ana/ai/models': MODELS,
    'GET /users/ana/ai': stateOf(OWN),
  });
  assert.match(el().textContent, /gasta unos céntimos/);
  el().querySelector('[data-act="test"]').click();
  await settle();
  await settle();
  assert.match(el().querySelector('[data-msg="model"]').textContent, /Funciona con gpt-4\.1-mini: Team Cherry/);
  assert.equal(log.filter((c) => c.path.endsWith('/test')).length, 1);
  installApi({ 'POST /users/ana/ai/test': () => json({ detail: 'OpenAI no acepta tu clave' }, 400) });
  el().querySelector('[data-act="test"]').click();
  await settle();
  await settle();
  assert.match(el().querySelector('[data-msg="model"]').textContent, /no acepta tu clave/);
});

test('removing the key goes back to the group paying where it covers, and asks the API again', async () => {
  let removed = false;
  const calls = await open({
    'DELETE /users/ana/ai': () => { removed = true; return NONE; },
    'GET /users/ana/ai/models': MODELS,
    'GET /users/ana/ai': () => json(stateOf(removed ? NONE : OWN)),
  });
  el().querySelector('[data-act="remove"]').click();
  await settle();
  await settle();
  assert.equal(calls.some((c) => c.method === 'DELETE'), true);
  assert.match(el().textContent, /Clave quitada/);
  assert.ok(el().querySelector('input[type="password"]'));
});

test('a key that cannot be opened any more asks for it again', async () => {
  await open({ 'GET /users/ana/ai': stateOf({ ...NONE, unreadable: true }) });
  assert.match(el().textContent, /No se puede abrir la clave que tenías guardada/);
  assert.ok(el().querySelector('input[type="password"]'));
});

test('a key can be replaced, and the change can be cancelled', async () => {
  await open({ 'GET /users/ana/ai/models': MODELS, 'GET /users/ana/ai': stateOf(OWN) });
  el().querySelector('[data-act="change"]').click();
  assert.match(el().querySelector('[data-form="key"]').textContent, /Clave nueva/);
  el().querySelector('[data-act="cancel"]').click();
  assert.equal(el().querySelector('[data-form="key"]'), null);
});

const USAGE = {
  total: figures(5, 0.75, { input_tokens: 2_500_000, output_tokens: 3000 }),
  by_source: [{ name: 'user', ...figures(2, 0.25) }, { name: 'group', ...figures(3, 0.5) }],
  by_feature: [{ name: 'guide', ...figures(2, 0.25) }, { name: 'chat', ...figures(3, 0.5) }],
  by_model: [{ name: 'openai/gpt-4.1-mini', ...figures(5, 0.75) }],
  by_status: [{ name: 'ok', calls: 5 }],
  months: [{ month: '2026-10', calls: 1, cost: 0.1, group_cost: 0.1, user_cost: 0, unpriced: 0 }, { month: '2026-11', calls: 4, cost: 0.65, group_cost: 0.4, user_cost: 0.25, unpriced: 0 }],
  days: [],
  budget: { month: '2026-11', resets_on: '2026-12-01', group: { cap: 20, spent: 8 }, user: { cap: 4, spent: 0.4 } },
};

test('the player sees what they paid with their own key against what the group covered, by function and by model, and by month', async () => {
  await open({ 'GET /users/ana/ai/usage': USAGE, 'GET /users/ana/ai': stateOf(NONE) });
  const spend = el().querySelector('[data-spend]');
  const tiles = [...spend.querySelectorAll('.pf-stat')].map((t) => t.textContent.replace(/\s+/g, ' ').trim());
  assert.match(tiles[0], /0,25.*Coste con tu clave/);
  assert.match(tiles[1], /0,50.*Coste cubierto por el grupo/);
  assert.match(tiles[2], /5\s*Preguntas/);
  assert.match(tiles[3], /2,5 M \/ 3\.?000/);
  assert.match(spend.querySelector('[data-by="feature"]').textContent, /Guía de juego[\s\S]*Chat/);
  assert.match(spend.querySelector('[data-by="model"]').textContent, /gpt-4\.1-mini/);
  const months = spend.querySelector('[data-by="month"]').textContent;
  assert.match(months, /Noviembre de 2026.*tu clave 0,25.*grupo 0,40/s);
  assert.match(spend.textContent, /no se guarda lo que escribes/);
});

test('choosing a month asks for that month and shows its days instead of the months', async () => {
  const log = await open({ 'GET /users/ana/ai/usage': USAGE, 'GET /users/ana/ai': stateOf(NONE) });
  installApi({
    'GET /users/ana/ai/usage?month=2026-11': { ...USAGE, days: [{ date: '2026-11-03', calls: 2, cost: 0.3 }] },
    'GET /users/ana/ai': stateOf(NONE),
  });
  const select = el().querySelector('select[name="spend-month"]');
  select.value = '2026-11';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  await settle();
  assert.ok(el().querySelector('[data-by="day"]').textContent.includes('2026-11-03'));
  assert.equal(el().querySelector('[data-by="month"]'), null);
  assert.ok(log.length >= 1);
});

test('without any use it says so instead of empty figures', async () => {
  await open({ 'GET /users/ana/ai': stateOf(NONE) });
  assert.match(el().querySelector('[data-spend]').textContent, /Todavía no has usado la IA/);
  assert.equal(el().querySelector('.pf-stats'), null);
});

test('the budget of the group and their share show with what is spent and when it starts again, and nothing without a cap', async () => {
  await open({ 'GET /users/ana/ai/usage': USAGE, 'GET /users/ana/ai': { ...stateOf(NONE), budget: USAGE.budget } });
  const text = el().querySelector('.ai-budget').textContent;
  assert.match(text, /Presupuesto del grupo este mes: 8,00.* de 20,00/);
  assert.match(text, /Tu parte: 0,40.* de 4,00/);
  assert.match(text, /Se renueva el 1 de diciembre/);
  await open({ 'GET /users/ana/ai': { ...stateOf(NONE), budget: NOTHING.budget } });
  assert.equal(el().querySelector('.ai-budget'), null);
});

test('when a budget stops the group key the player is told, and told how to go on if they have no key', async () => {
  const blocked = { ...stateOf(NONE), chat: { available: true, needs_key: true, paid_by: null, mode: 'group_then_user', blocked: 'group' } };
  await open({ 'GET /users/ana/ai': blocked });
  assert.match(el().textContent, /Se ha agotado el presupuesto de IA del grupo este mes/);
  assert.match(el().textContent, /puedes seguir con tu propia clave/);
  await open({ 'GET /users/ana/ai/models': MODELS, 'GET /users/ana/ai': { ...blocked, key: OWN, chat: { ...blocked.chat, blocked: 'user' } } });
  assert.match(el().textContent, /Has gastado tu parte del presupuesto/);
  assert.doesNotMatch(el().textContent, /puedes seguir con tu propia clave/);
});

test('a message of the key box survives the screen being drawn again when the spending arrives', async () => {
  await open({ 'GET /users/ana/ai': stateOf(NONE) });
  await submitKey('hola');
  await settle();
  assert.match(el().querySelector('[data-msg="key"]').textContent, /empieza por sk-/);
});

test('the explanation of the key says what it is for in the order that is true: the guide, and the chat once the group budget is spent', async () => {
  await open({ 'GET /users/ana/ai': stateOf(NONE) });
  const text = el().textContent;
  assert.match(text, /Con tu propia clave puedes usar la guía de cada juego y seguir con el chat cuando se agote el presupuesto del grupo \(o tu parte\)/);
  assert.doesNotMatch(text, /en lugar de sumarse al del grupo/);
});
