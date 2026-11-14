import assert from 'node:assert/strict';
import { beforeEach, test } from 'node:test';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
const window = installDom('<div id="pfAi"></div>', 'http://localhost/');
globalThis.location = window.location;
const { initAi } = await import('../js/pages/profile/ai.js');

const KEYS = {
  openai: 'sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789',
  anthropic: 'sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789',
  google: 'AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz0123456',
};
const EMPTY = { has_key: false, unreadable: false, hint: null, model: null };
const own = (hint, model) => ({ has_key: true, unreadable: false, hint, model });
const keysOf = (extra = {}) => ({ openai: EMPTY, anthropic: EMPTY, google: EMPTY, openrouter: EMPTY, ...extra });
const hasAny = (keys) => Object.values(keys).some((k) => k.has_key);
const stateOf = (keys = keysOf(), extra = {}) => ({
  unlocked: true,
  locked: false,
  preferred: null,
  keys,
  default_models: { openai: 'gpt-4.1-mini', google: 'gemini-3.5-flash-lite', anthropic: 'claude-haiku-5-5', openrouter: 'openai/gpt-4.1-mini' },
  chat: { available: true, needs_key: false, paid_by: 'group', mode: 'group_then_user', blocked: null, locked: false }, // the group's first, with a key or not
  guide: { available: true, needs_key: !hasAny(keys), paid_by: hasAny(keys) ? 'user' : null, mode: 'user_only', blocked: null, locked: false },
  ...extra,
});
const OWN = stateOf(keysOf({ openai: own('6789', 'gpt-4.1-mini') }));
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
  budget: { month: '2026-11', resets_on: '2026-12-01', user: { cap: null, spent: 0 } },
};
const el = () => document.getElementById('pfAi');
const card = (provider) => el().querySelector(`[data-provider="${provider}"].ai-provider`);
const open = async (routes) => {
  el().replaceWith(el().cloneNode(false)); // a new element: the listeners of the screen before it go with the old one
  // the longer path first: a route matches by its start
  const calls = installApi({ 'GET /users/ana/ai/usage': NOTHING, ...routes });
  await initAi(el(), { username: 'ana' });
  await settle();
  return calls;
};
const submitKey = async (provider, value) => {
  card(provider).querySelector('[name="api_key"]').value = value;
  card(provider).querySelector('[data-form="key"]').requestSubmit();
  await settle();
  await settle();
};
const sent = (calls, method, path) => calls.filter((c) => c.method === method && (!path || c.path === path)).map((c) => c.body);

beforeEach(() => {
  el().replaceWith(el().cloneNode(false));
  localStorage.removeItem('lv_token');
});

test('without keys it says, quietly, where the cost goes, offers a card for each provider and loads no models', async () => {
  const calls = await open({ 'GET /users/ana/ai': stateOf() });
  const note = el().querySelector('.ai-cost-note').textContent;
  assert.match(note, /El coste del chat lo cubre el grupo mientras haya saldo; después necesitarás tu propia clave/);
  assert.match(note, /La guía de cada juego busca en internet y cuesta más: funciona con tu propia clave/);
  assert.deepEqual([...el().querySelectorAll('.ai-provider h3')].map((h) => h.textContent), ['OpenAI', 'Anthropic (Claude)', 'Google (Gemini)', 'OpenRouter']);
  assert.equal(el().querySelectorAll('input[type="password"][name="api_key"]').length, 4);
  assert.equal(el().querySelector('select[name="model"]'), null);
  assert.equal(el().querySelector('[data-preferred]'), null, 'nothing to prefer without a key');
  assert.equal(el().querySelector('[data-locked]'), null, 'an unlocked session has no password box');
  assert.equal(calls.some((c) => c.path.endsWith('/models')), false);
});

test('a session that cannot open the keys says so, shows what is saved without its details and asks for the password', async () => {
  await open({ 'GET /users/ana/ai': stateOf(keysOf({ openai: own(null, 'gpt-4.1-mini') }), { unlocked: false, locked: true }) });
  const box = el().querySelector('[data-locked]');
  assert.match(box.textContent, /Tus claves están bloqueadas en esta sesión/);
  assert.match(card('openai').textContent, /Clave guardada(?! , termina)/);
  assert.doesNotMatch(card('openai').textContent, /termina en/, 'the last characters are inside the vault');
  assert.equal(card('google').querySelector('[name="api_key"]').disabled, true, 'nothing can be saved while locked');
  assert.equal(card('openai').querySelector('[data-act="change"]').disabled, true);
  assert.equal(el().querySelector('select[name="model"]'), null, 'no models are asked while locked');
});

test('a player with no keys yet is asked for the password once, to be able to save the first one', async () => {
  await open({ 'GET /users/ana/ai': stateOf(keysOf(), { unlocked: false }) });
  assert.match(el().querySelector('[data-locked]').textContent, /Para guardar una clave, confirma tu contraseña/);
  assert.equal(card('openai').querySelector('[name="api_key"]').disabled, true);
});

test('the password opens the session: the new token replaces the old one, the box goes away and the keys and models appear', async () => {
  localStorage.setItem('lv_token', 'old-token');
  const calls = await open({
    'POST /users/ana/ai/unlock': { access_token: 'new-token', token_type: 'bearer', ...OWN },
    'GET /users/ana/ai/openai/models': MODELS,
    'GET /users/ana/ai': stateOf(keysOf({ openai: own(null, 'gpt-4.1-mini') }), { unlocked: false, locked: true }),
  });
  el().querySelector('[data-locked] [name="password"]').value = 'La-Contrasena-1!';
  el().querySelector('[data-form="unlock"]').requestSubmit();
  await settle();
  await settle();
  assert.deepEqual(sent(calls, 'POST', '/users/ana/ai/unlock'), [{ password: 'La-Contrasena-1!' }]);
  assert.equal(localStorage.getItem('lv_token'), 'new-token');
  assert.equal(el().querySelector('[data-locked]'), null);
  assert.match(el().textContent, /Clave guardada, termina en …6789/);
  assert.ok(el().querySelector('select[name="model"]'));
  assert.equal(el().textContent.includes('new-token'), false);
});

test('a wrong password says so, keeps the session locked and keeps the old token', async () => {
  localStorage.setItem('lv_token', 'old-token');
  await open({
    'POST /users/ana/ai/unlock': () => json({ detail: 'Contraseña incorrecta' }, 400),
    'GET /users/ana/ai': stateOf(keysOf({ openai: own(null, 'gpt-4.1-mini') }), { unlocked: false, locked: true }),
  });
  el().querySelector('[data-locked] [name="password"]').value = 'nope';
  el().querySelector('[data-form="unlock"]').requestSubmit();
  await settle();
  await settle();
  assert.match(el().querySelector('[data-msg="unlock"]').textContent, /Contraseña incorrecta/);
  assert.equal(el().querySelector('[data-locked] [name="password"]').value, '', 'the password is not left in the box');
  assert.equal(localStorage.getItem('lv_token'), 'old-token');
  assert.ok(el().querySelector('[data-locked]'));
});

test('what is typed that does not look like a key of that provider is not even sent, and another provider\'s key is refused', async () => {
  const calls = await open({ 'GET /users/ana/ai': stateOf() });
  await submitKey('openai', 'hola');
  assert.match(card('openai').querySelector('[data-msg="openai"]').textContent, /Eso no parece una clave de OpenAI: empieza por sk-/);
  await submitKey('openai', KEYS.anthropic);
  assert.match(card('openai').querySelector('[data-msg="openai"]').textContent, /no parece una clave de OpenAI/);
  await submitKey('anthropic', KEYS.openai);
  assert.match(card('anthropic').querySelector('[data-msg="anthropic"]').textContent, /Anthropic \(Claude\): empieza por sk-ant-/);
  assert.deepEqual(sent(calls, 'PUT'), []);
});

test('a key is saved for its provider, then only its last characters and its model show, and the models of that account are offered', async () => {
  let saved = false;
  const calls = await open({
    'PUT /users/ana/ai/anthropic': () => { saved = true; return stateOf(); },
    'GET /users/ana/ai/anthropic/models': { models: [{ id: 'claude-haiku-5-5', tier: 'economico', input_per_million: 1, output_per_million: 5 }], current: 'claude-haiku-5-5' },
    'GET /users/ana/ai': () => json(saved ? stateOf(keysOf({ anthropic: own('6789', 'claude-haiku-5-5') })) : stateOf()),
  });
  await submitKey('anthropic', ` ${KEYS.anthropic} `);
  assert.deepEqual(sent(calls, 'PUT', '/users/ana/ai/anthropic'), [{ api_key: KEYS.anthropic }]);
  assert.match(card('anthropic').textContent, /Clave guardada, termina en …6789/);
  assert.match(card('anthropic').textContent, /modelo claude-haiku-5-5/);
  assert.match(card('openai').textContent, /Sin clave de OpenAI/, 'the others are untouched');
  const kept = el().querySelector('.ai-cost-note').textContent;
  assert.match(kept, /después seguirá con tu clave/);
  assert.match(kept, /El coste de la guía va a tu cuenta del proveedor de tu clave/);
  assert.equal(el().textContent.includes(KEYS.anthropic), false, 'the key is never drawn');
  assert.equal(card('anthropic').querySelector('input[type="password"]'), null, 'the box goes away once it is saved');
  assert.ok(calls.some((c) => c.path === '/users/ana/ai/anthropic/models'));
  assert.ok(el().querySelector('[data-preferred]'), 'now there is a key to prefer');
});

test('a key that its provider refuses shows the reason and leaves the box empty, never repeating the key', async () => {
  await open({
    'PUT /users/ana/ai/google': () => json({ detail: 'Google no acepta esa clave.' }, 400),
    'GET /users/ana/ai': stateOf(),
  });
  await submitKey('google', KEYS.google);
  assert.match(card('google').querySelector('[data-msg="google"]').textContent, /Google no acepta esa clave/);
  assert.equal(card('google').querySelector('[name="api_key"]').value, '');
  assert.equal(el().textContent.includes(KEYS.google), false);
});

test('a save that answers locked asks the state again and shows the password box', async () => {
  let locked = false;
  await open({
    'PUT /users/ana/ai/openai': () => { locked = true; return json({ detail: 'Tus claves de IA están bloqueadas en esta sesión' }, 423); },
    'GET /users/ana/ai': () => json(locked ? stateOf(keysOf(), { unlocked: false }) : stateOf()),
  });
  await submitKey('openai', KEYS.openai);
  assert.ok(el().querySelector('[data-locked]'));
  assert.match(el().querySelector('[data-msg="unlock"]').textContent, /bloqueadas/);
});

test('choosing another model sends only the model to that provider, in a box that searches', async () => {
  const calls = await open({
    'PUT /users/ana/ai/openai': ({ body }) => stateOf(keysOf({ openai: own('6789', body.model) })),
    'GET /users/ana/ai/openai/models': MODELS,
    'GET /users/ana/ai': OWN,
  });
  const select = card('openai').querySelector('select[name="model"]');
  assert.equal(select.hidden, true, 'the select is the field and a box that searches is what is seen');
  assert.ok(card('openai').querySelector('.adm-combo-input'));
  select.value = 'gpt-5';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  await settle();
  assert.deepEqual(sent(calls, 'PUT'), [{ model: 'gpt-5' }]);
  assert.match(card('openai').querySelector('[data-msg="openai"]').textContent, /Modelo guardado: gpt-5/);
});

test('the models of the list carry their price and a model that is not in the list is still shown, as the one they have', async () => {
  await open({
    'GET /users/ana/ai/openai/models': MODELS,
    'GET /users/ana/ai': stateOf(keysOf({ openai: own('6789', 'my-custom-model') })),
  });
  const select = card('openai').querySelector('select[name="model"]');
  assert.equal(select.value, 'my-custom-model');
  assert.deepEqual([...select.options].map((o) => o.value), ['my-custom-model', 'gpt-4.1-mini', 'gpt-5']);
  assert.match([...select.options][2].textContent, /gpt-5 · precio medio · 1,25.*10,00/);
});

test('the test of a provider says it spends a little, and shows the answer or the error in its own card', async () => {
  const log = await open({
    'POST /users/ana/ai/openai/test': { reply: 'Team Cherry', model: 'gpt-4.1-mini', provider: 'openai' },
    'GET /users/ana/ai/openai/models': MODELS,
    'GET /users/ana/ai': OWN,
  });
  assert.match(card('openai').textContent, /gasta unos céntimos/);
  card('openai').querySelector('[data-act="test"]').click();
  await settle();
  await settle();
  assert.match(card('openai').querySelector('[data-msg="openai"]').textContent, /Funciona con gpt-4\.1-mini: Team Cherry/);
  assert.equal(log.filter((c) => c.path.endsWith('/test')).length, 1);
  installApi({ 'POST /users/ana/ai/openai/test': () => json({ detail: 'OpenAI no acepta tu clave' }, 400) });
  card('openai').querySelector('[data-act="test"]').click();
  await settle();
  await settle();
  assert.match(card('openai').querySelector('[data-msg="openai"]').textContent, /no acepta tu clave/);
});

test('removing a key goes back to the group paying where it covers, leaves the others and asks the API again', async () => {
  let removed = false;
  const both = stateOf(keysOf({ openai: own('6789', 'gpt-4.1-mini'), google: own('3456', 'gemini-3.5-flash-lite') }));
  const calls = await open({
    'DELETE /users/ana/ai/openai': () => { removed = true; return stateOf(); },
    'GET /users/ana/ai/openai/models': MODELS,
    'GET /users/ana/ai/google/models': { models: [], current: 'gemini-3.5-flash-lite' },
    'GET /users/ana/ai': () => json(removed ? stateOf(keysOf({ google: own('3456', 'gemini-3.5-flash-lite') })) : both),
  });
  card('openai').querySelector('[data-act="remove"]').click();
  await settle();
  await settle();
  assert.equal(calls.some((c) => c.method === 'DELETE' && c.path === '/users/ana/ai/openai'), true);
  assert.match(card('openai').querySelector('[data-msg="openai"]').textContent, /Clave quitada/);
  assert.ok(card('openai').querySelector('input[type="password"]'));
  assert.match(card('google').textContent, /termina en …3456/);
});

test('a key that cannot be opened any more asks for it again', async () => {
  await open({ 'GET /users/ana/ai': stateOf(keysOf({ openai: { has_key: true, unreadable: true, hint: null, model: 'gpt-4.1-mini' } })) });
  assert.match(card('openai').textContent, /No se puede abrir la clave que tenías guardada/);
});

test('a key can be replaced, and the change can be cancelled', async () => {
  await open({ 'GET /users/ana/ai/openai/models': MODELS, 'GET /users/ana/ai': OWN });
  card('openai').querySelector('[data-act="change"]').click();
  assert.match(card('openai').querySelector('[data-form="key"]').textContent, /Clave nueva/);
  card('openai').querySelector('[data-act="cancel"]').click();
  assert.equal(card('openai').querySelector('[data-form="key"]'), null);
});

test('with keys the player can say which provider comes first, and go back to the app choosing', async () => {
  const both = stateOf(keysOf({ openai: own('6789', 'gpt-4.1-mini'), google: own('3456', 'gemini-3.5-flash-lite') }));
  const calls = await open({
    'PUT /users/ana/ai/preferred': ({ body }) => ({ ...both, preferred: body.provider }),
    'GET /users/ana/ai/openai/models': MODELS,
    'GET /users/ana/ai/google/models': { models: [], current: 'gemini-3.5-flash-lite' },
    'GET /users/ana/ai': both,
  });
  const select = el().querySelector('select[name="preferred"]');
  assert.deepEqual([...select.options].map((o) => o.value), ['', 'openai', 'google'], 'only the providers with a key');
  select.value = 'google';
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  await settle();
  assert.deepEqual(sent(calls, 'PUT', '/users/ana/ai/preferred'), [{ provider: 'google' }]);
  assert.match(el().querySelector('[data-msg="preferred"]').textContent, /Se usará primero la clave de Google/);
  el().querySelector('select[name="preferred"]').value = '';
  el().querySelector('select[name="preferred"]').dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  await settle();
  assert.deepEqual(sent(calls, 'PUT', '/users/ana/ai/preferred').at(-1), { provider: null });
});

const USAGE = {
  total: figures(5, 0.75, { input_tokens: 2_500_000, output_tokens: 3000 }),
  by_source: [{ name: 'user', ...figures(2, 0.25) }, { name: 'group', ...figures(3, 0.5) }],
  by_feature: [{ name: 'guide', ...figures(2, 0.25) }, { name: 'chat', ...figures(3, 0.5) }],
  by_model: [{ name: 'openai/gpt-4.1-mini', ...figures(5, 0.75) }],
  by_status: [{ name: 'ok', calls: 5 }],
  months: [{ month: '2026-10', calls: 1, cost: 0.1, group_cost: 0.1, user_cost: 0, unpriced: 0 }, { month: '2026-11', calls: 4, cost: 0.65, group_cost: 0.4, user_cost: 0.25, unpriced: 0 }],
  days: [],
  budget: { month: '2026-11', resets_on: '2026-12-01', user: { cap: 4, spent: 0.4 } },
};

test('the player sees what they paid with their own key against what the group covered, by function and by model, and by month', async () => {
  await open({ 'GET /users/ana/ai/usage': USAGE, 'GET /users/ana/ai': stateOf() });
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
  assert.match(el().textContent, /no se guarda lo que escribes/); // in the "i" of the title
});

test('choosing a month asks for that month and shows its days instead of the months', async () => {
  const log = await open({ 'GET /users/ana/ai/usage': USAGE, 'GET /users/ana/ai': stateOf() });
  installApi({
    'GET /users/ana/ai/usage?month=2026-11': { ...USAGE, days: [{ date: '2026-11-03', calls: 2, cost: 0.3 }] },
    'GET /users/ana/ai': stateOf(),
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
  await open({ 'GET /users/ana/ai': stateOf() });
  assert.match(el().querySelector('[data-spend]').textContent, /Todavía no has usado la IA/);
  assert.equal(el().querySelector('.pf-stats'), null);
});

test('the monthly cap is not shown for now: only the wallet line is', async () => {
  await open({ 'GET /users/ana/ai/usage': USAGE, 'GET /users/ana/ai': { ...stateOf(), budget: USAGE.budget } });
  assert.equal(el().querySelector('.ai-budget'), null);
  assert.doesNotMatch(el().textContent, /Tu parte de la IA del grupo este mes/);
});

test('the wallet balance shows when there is one', async () => {
  await open({ 'GET /users/ana/ai': { ...stateOf(), wallet: { contributed: 3, spent: 1, balance: 2, since: '2026-11-10' } } });
  assert.match(el().querySelector('.ai-budget').textContent, /Tu saldo de IA del grupo: 2,00/);
});

test('when their share or balance stops the group key the player is told, and told how to go on if they have no key', async () => {
  const blocked = { ...stateOf(), chat: { available: true, needs_key: true, paid_by: null, mode: 'group_then_user', blocked: 'user', locked: false } };
  await open({ 'GET /users/ana/ai': blocked });
  assert.match(el().textContent, /Has gastado tu parte de la IA del grupo este mes/);
  assert.match(el().textContent, /puedes seguir con una clave tuya/);
  await open({ 'GET /users/ana/ai/openai/models': MODELS, 'GET /users/ana/ai': { ...blocked, keys: OWN.keys, chat: { ...blocked.chat, paid_by: 'user', blocked: null } } });
  assert.doesNotMatch(el().textContent, /Has gastado tu parte/);
  assert.doesNotMatch(el().textContent, /puedes seguir con una clave tuya/);
  await open({ 'GET /users/ana/ai': { ...blocked, chat: { ...blocked.chat, blocked: 'user_off' } } });
  assert.match(el().textContent, /Un admin no te ha dado IA de la clave del grupo/);
});

test('a message of a key box survives the screen being drawn again when the spending arrives', async () => {
  await open({ 'GET /users/ana/ai': stateOf() });
  await submitKey('openai', 'hola');
  await settle();
  assert.match(card('openai').querySelector('[data-msg="openai"]').textContent, /empieza por sk-/);
});

test('what was being typed in a key box survives a redraw', async () => {
  await open({ 'GET /users/ana/ai': stateOf() });
  card('google').querySelector('[name="api_key"]').value = 'AIza-a-half-typed-key';
  card('google').querySelector('[data-act="change"]')?.click(); // nothing to change: no card of a key to open
  el().querySelector('select[name="spend-month"]');
  card('openai').querySelector('[name="api_key"]').value = 'sk-another';
  const select = el().querySelector('[name="spend-month"]');
  if (select) select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  assert.equal(card('google').querySelector('[name="api_key"]').value, 'AIza-a-half-typed-key');
});

test('the explanation of the keys says what they are for in the order that is true and that they are sealed with the password', async () => {
  await open({ 'GET /users/ana/ai': stateOf() });
  const text = el().textContent;
  assert.match(text, /Con tu propia clave puedes usar la guía de cada juego y seguir con el chat cuando se agote el saldo del grupo \(o tu parte del mes\)/);
  assert.match(text, /cifrada con tu contraseña/);
  assert.match(text, /las claves se borran/);
  assert.doesNotMatch(text, /en lugar de sumarse al del grupo/);
});

test('the screen explains what the chat does and what the guide does, with the cost of each and what the guide adds', async () => {
  await open({ 'GET /users/ana/ai': stateOf() });
  const chat = el().querySelector('[data-about="chat"]').textContent;
  const guide = el().querySelector('[data-about="guide"]').textContent;
  assert.match(chat, /Responde sobre los datos del grupo/);
  assert.match(chat, /Coste\..*fracción de céntimo/);
  assert.match(guide, /empujón.*pista.*solución/);
  assert.match(guide, /Qué aporta frente a preguntárselo directamente a ChatGPT/);
  assert.match(guide, /No sabe más que ChatGPT/);
  assert.match(guide, /Coste\..*se cobran aparte/);
  assert.ok([...el().querySelectorAll('h2')].some((h) => /Qué hacen el chat y la guía/.test(h.textContent)));
});

test('what the chat and the guide do is folded until the player opens it, and stays as they left it when the screen is drawn again', async () => {
  await open({ 'GET /users/ana/ai/openai/models': MODELS, 'GET /users/ana/ai': OWN });
  const fold = () => el().querySelector('[data-about-fold]');
  assert.equal(fold().open, false, 'closed by default: it takes no room');
  assert.match(fold().querySelector('summary').textContent, /Qué hacen el chat y la guía/);
  fold().open = true;
  fold().dispatchEvent(new window.Event('toggle'));
  const select = el().querySelector('select[name="spend-month"]') ?? el().querySelector('select[name="preferred"]');
  select.value = select.options[select.options.length - 1].value;
  select.dispatchEvent(new window.Event('change', { bubbles: true }));
  await settle();
  await settle();
  assert.equal(fold().open, true, 'a redraw does not fold it again');
});

test('the explanations of the keys and the spending are one tap away in an "i" beside their titles, not paragraphs under them', async () => {
  await open({ 'GET /users/ana/ai/openai/models': MODELS, 'GET /users/ana/ai': OWN });
  const heads = [...el().querySelectorAll('.pf-info-title')];
  assert.deepEqual(heads.map((h) => h.querySelector('h2').textContent), ['Tus claves de IA', 'Tu gasto']);
  for (const head of heads) {
    assert.ok(head.querySelector('summary[aria-label]'), 'a button with a name');
    assert.ok(head.querySelector('.pf-info-text').textContent.length > 40, 'with its explanation');
  }
});

test('the safety advice about a spending limit is still seen in each card without opening anything', async () => {
  await open({ 'GET /users/ana/ai': stateOf() });
  assert.match(card('openai').querySelector('[data-form="key"]').textContent, /límite de gasto mensual/);
  assert.match(card('openrouter').querySelector('[data-form="key"]').textContent, /límite de crédito/);
  assert.match(card('google').querySelector('[data-form="key"]').textContent, /plan de pago/);
  assert.ok(card('anthropic').querySelector('a[href^="https://platform.claude.com"]'));
});
