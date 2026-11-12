import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { render } = await import('../js/pages/admin/settings.js');

const VALUES = {
  'ai.enabled': true, 'ai.provider': null, 'ai.openai.api_key': { is_set: true }, 'ai.google.api_key': { is_set: true }, 'ai.openai_admin_key': { is_set: false },
  'ai.model.openai': null, 'ai.model.google': null, 'chat.model.openai': null, 'chat.model.google': null,
  'ai.use.completed_game': true, 'ai.use.new_game': false, 'chat.enabled': true, 'chat.prompt': 'd',
  'chat.limit_user_minute': 5, 'chat.limit_user_hour': 30, 'chat.limit_user_day': 100, 'chat.limit_group_minute': 10, 'chat.limit_group_day': 300, 'completed_game.recommend': true,
  'telegram.token': { is_set: false }, 'telegram.group_id': { is_set: false }, 'telegram.admin_chat_id': { is_set: false }, 'push.vapid_private': { is_set: true },
  'ai.prompt.completed_game': 'a', 'ai.prompt.completed_game_recommendation': 'b', 'ai.prompt.new_game': 'c',
};
const CHAT = { provider: 'openai', model: 'gpt-chat', own_model: true, default_prompt: 'd', customized: false };
// what the .env has: both providers with a key; the one in use is Google's, with its default model
const providersOf = (inUse = 'google', keys = ['openai', 'google'], models = {}) => ({
  providers: ['openai', 'google'].map((id) => ({ id, has_key: keys.includes(id), default_model: models[id] ?? (id === 'google' ? 'gemini-test' : 'gpt-test'), default_chat_model: models[id] ?? (id === 'google' ? 'gemini-test' : 'gpt-test') })),
  provider: inUse, picked: null, notices_model: 'gemini-test', chat_model: 'gemini-test', notices_own: false, chat_own: false,
});
const MODEL_LIST = { provider: 'google', models: ['gemini-2.5-flash', 'gemini-2.5-pro'], defaults: { notices: 'gemini-test', chat: 'gemini-test' } };
const USES = [
  { id: 'new_game', label: 'Empieza un juego', help: 'h1', switchable: true, switch: 'ai.use.new_game', parent: null, default_prompt: 'c', customized: false },
  { id: 'completed_game', label: 'Completa un juego', help: 'h2', switchable: true, switch: 'ai.use.completed_game', parent: null, default_prompt: 'a', customized: true },
  { id: 'completed_game_recommendation', label: 'Recomendación al completar', help: 'h3', switchable: false, switch: 'completed_game.recommend', parent: 'completed_game', default_prompt: 'b', customized: true },
];

const panel = () => document.getElementById('panel');
const open = async (values = VALUES, model = 'gemini-test') => {
  installApi({
    'GET /manage/settings/ai-models': MODEL_LIST,
    'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model }, ai_providers: providersOf(), chat: CHAT },
  });
  await render(panel(), { entity: { sections: ['ai', 'aiuses'] } });
  await settle();
  await settle(); // the list of models is asked after the page is drawn
};

test('a fragment is drawn inside the notice it belongs to, with its own switch', async () => {
  await open();
  const rows = [...panel().querySelectorAll('.adm-ai-uses > .adm-ai-use')];
  assert.equal(rows.length, 2, 'only the notices are top-level rows');
  const completed = rows[1];
  const fragment = completed.querySelector('.adm-ai-fragment');
  assert.match(fragment.textContent, /Recomendación al completar/);
  assert.equal(fragment.querySelector('input[type="checkbox"]').name, 'completed_game.recommend');
  assert.equal(panel().querySelectorAll('.adm-ai-uses input[type="checkbox"]').length, 3);
});

test('a changed notice says so and offers the original; one that was not changed does not', async () => {
  await open();
  const [untouched, changed] = [...panel().querySelectorAll('.adm-ai-uses > .adm-ai-use')];
  assert.equal(untouched.querySelector('.adm-tag'), null);
  assert.equal(untouched.querySelector('[data-set-act="reset-prompt"]'), null);
  assert.equal(changed.querySelector('.adm-tag').textContent, 'Personalizado');
  assert.ok(changed.querySelector('[data-set-act="reset-prompt"][data-use="completed_game"]'));
});

test('the notices are dimmed and the page says why while the general AI switch is off', async () => {
  await open({ ...VALUES, 'ai.enabled': false });
  assert.ok(panel().querySelector('.adm-ai-uses').classList.contains('off'));
  assert.equal(panel().querySelector('.adm-ai-off').hidden, false);
  const general = panel().querySelector('[name="ai.enabled"]');
  general.checked = true;
  general.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(panel().querySelector('.adm-ai-uses').classList.contains('off'), false);
  assert.equal(panel().querySelector('.adm-ai-off').hidden, true);
});

const answer = (values, aiModel, chat, aiProviders = providersOf()) => ({ values, jobs: {}, push_devices: { devices: 2, users: 1 }, mail: { configured: false, missing: [], test_recipient: null }, ai_uses: USES, ai_model: aiModel, ai_providers: aiProviders, chat });
const GOOGLE = { provider: 'google', model: 'gemini-test' };
const openSections = async (sections, values = VALUES, aiModel = GOOGLE, chat = CHAT, aiProviders = providersOf()) => {
  installApi({ 'GET /manage/settings/ai-models': MODEL_LIST, 'GET /manage/settings': answer(values, aiModel, chat, aiProviders) });
  await render(panel(), { entity: { sections } });
  await settle();
  await settle(); // the list of models is asked after the page is drawn
};

test('IA → Avisos con IA has the switch, the test, the provider picker and the model picker', async () => {
  await open();
  assert.equal(panel().querySelector('[name="ai.enabled"]').type, 'checkbox');
  assert.ok(panel().querySelector('[data-set-act="test-ai"]'));
  const provider = panel().querySelector('select[name="ai.provider"]');
  assert.deepEqual([...provider.options].map((o) => o.value), ['openai', 'google']); // both have a key in the .env
  assert.equal(provider.value, 'google'); // the one in use
  assert.equal(provider.disabled, false);
  const model = panel().querySelector('select[name="ai.model.google"]');
  assert.equal(model.value, ''); // the .env's model, until another is picked
  assert.match(model.options[0].textContent, /Por defecto \(gemini-test\)/);
  assert.deepEqual([...model.options].map((o) => o.value), ['', 'gemini-2.5-flash', 'gemini-2.5-pro']); // asked live to the provider
  assert.equal(panel().querySelectorAll('input:disabled').length, 1); // the admin key of OpenAI: nothing to type
  assert.match(panel().textContent, /Usa Google \(Gemini\) \(gemini-test\)/);
  assert.equal(panel().querySelector('.adm-warn'), null);
});

test('with the key of one provider only there is nothing to choose, and with none the page says which to define', async () => {
  await openSections(['ai', 'aiuses'], VALUES, GOOGLE, CHAT, providersOf('google', ['google']));
  const provider = panel().querySelector('select[name="ai.provider"]');
  assert.deepEqual([...provider.options].map((o) => o.value), ['google']);
  assert.equal(provider.disabled, true);
  await openSections(['ai', 'aiuses'], VALUES, { provider: null, model: null }, CHAT, providersOf(null, []));
  assert.equal(panel().querySelector('select[name="ai.provider"]'), null);
  assert.equal(panel().querySelector('select[name^="ai.model."]'), null);
  assert.match(panel().querySelector('.adm-warn').textContent, /OPENAI_AI_API_KEY o GOOGLE_AI_API_KEY/);
  assert.equal(panel().querySelector('[data-set-act="test-ai"]').disabled, true);
});

test('picking a provider and a model sends them; going back to the default sends null', async () => {
  await open();
  const form = panel().querySelector('#admSettings');
  form.elements['ai.provider'].value = 'openai';
  form.elements['ai.model.google'].value = 'gemini-2.5-pro';
  let saved = null;
  installApi({
    'GET /manage/settings/ai-models': MODEL_LIST,
    'GET /manage/settings': answer(VALUES, GOOGLE, CHAT),
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: [], values: VALUES }; },
  });
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const picks = () => Object.fromEntries(Object.entries(saved.values).filter(([key]) => /^ai\.(provider|model\.)|^chat\.model\./.test(key)));
  assert.deepEqual(picks(), { 'ai.provider': 'openai', 'ai.model.google': 'gemini-2.5-pro' });
  // a pick already stored goes back to the .env's model with an empty choice
  const stored = { ...VALUES, 'ai.model.google': 'gemini-2.5-pro' };
  installApi({ 'GET /manage/settings/ai-models': MODEL_LIST, 'GET /manage/settings': answer(stored, GOOGLE, CHAT) });
  await render(panel(), { entity: { sections: ['ai', 'aiuses'] } });
  await settle();
  await settle();
  const again = panel().querySelector('#admSettings');
  assert.equal(again.elements['ai.model.google'].value, 'gemini-2.5-pro');
  again.elements['ai.model.google'].value = '';
  installApi({ 'GET /manage/settings/ai-models': MODEL_LIST, 'GET /manage/settings': answer(stored, GOOGLE, CHAT), 'PUT /manage/settings': ({ body }) => { saved = body; return { changed: [], values: stored }; } });
  again.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(picks(), { 'ai.model.google': null });
});

test('when the provider cannot list its models the page says so and keeps the default', async () => {
  installApi({
    'GET /manage/settings/ai-models': () => { throw new Error('google no ha dado la lista de modelos'); },
    'GET /manage/settings': answer(VALUES, GOOGLE, CHAT),
  });
  await render(panel(), { entity: { sections: ['ai', 'aiuses'] } });
  await settle();
  assert.match(panel().querySelector('.adm-model-note').textContent, /No se ha podido consultar la lista de modelos/);
  assert.equal(panel().querySelector('select[name="ai.model.google"]').options.length, 1);
});

test('saving the AI switch never sends the provider, the key or the model', async () => {
  await open();
  const form = panel().querySelector('#admSettings');
  form.querySelector('[name="ai.enabled"]').checked = false;
  let saved = null;
  installApi({
    'GET /manage/settings/ai-models': MODEL_LIST,
    'GET /manage/settings': answer(VALUES, GOOGLE, CHAT),
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: [], values: VALUES }; },
  });
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(saved.values['ai.enabled'], false);
  assert.deepEqual(Object.keys(saved.values).filter((key) => /provider|api_key|model/.test(key)), []);
});

test('without a model the page says the AI writes nothing and which one is missing', async () => {
  await openSections(['ai', 'aiuses'], VALUES, { provider: 'google', model: null });
  assert.match(panel().querySelector('.adm-warn').textContent, /Falta un modelo \(GOOGLE_AI_MODEL en el \.env, o elígelo aquí\)/);
  assert.equal(panel().querySelectorAll('.adm-warn').length, 1); // said once, not once per card
});

test('Canales holds Telegram, the app notices (with their contact and keys) and the mail, each in one card', async () => {
  await openSections(['telegram', 'push', 'mail']);
  assert.equal(panel().querySelectorAll('.adm-set-card').length, 3);
  assert.equal(panel().querySelectorAll('input[disabled]').length, 3); // the bot's token and two ids, read only
  assert.ok(panel().querySelector('[data-set-act="test"]'));
  assert.equal(panel().querySelector('[name="push.enabled"]').type, 'checkbox');
  assert.ok(panel().querySelector('[name="push.contact"]'));
  assert.ok(panel().querySelector('[data-set-act="push-keys"]'));
  assert.ok(panel().querySelector('[data-set-act="test-email"]'));
  assert.equal(panel().querySelector('.adm-ai-provider'), null); // the AI is not here
});

test('Canales says whether Telegram is set and only allows the test when it is', async () => {
  await openSections(['telegram']);
  assert.match(panel().querySelector('.adm-warn').textContent, /faltan TELEGRAM_TOKEN y TELEGRAM_GROUP_ID/);
  assert.equal(panel().querySelector('[data-set-act="test"]').disabled, true);
  await openSections(['telegram'], { ...VALUES, 'telegram.token': { is_set: true }, 'telegram.group_id': { is_set: true } });
  assert.equal(panel().querySelector('.adm-warn'), null);
  assert.equal(panel().querySelector('[data-set-act="test"]').disabled, false);
});

const openWithChat = async (values = VALUES, chat = CHAT, aiProviders = providersOf()) => {
  installApi({ 'GET /manage/settings/ai-models': MODEL_LIST, 'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, ai_providers: aiProviders, chat } });
  await render(panel(), { entity: { sections: ['chat'] } });
  await settle();
  await settle(); // the list of models is asked after the page is drawn
};
const openLimits = async (values = VALUES, sections = ['ailimitq']) => {
  installApi({ 'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT, guide: CHAT } });
  await render(panel(), { entity: { sections } });
  await settle();
  await settle(); // the list of models is asked after the page is drawn
};
const limitsCard = () => panel().querySelector('.adm-ailimitq-card');
const chatCard = () => panel().querySelector('.adm-chat-card');
const state = () => chatCard().querySelector('.adm-chat-state').textContent;

test('the chat card shows its switch, its instructions and a picker for the model it uses', async () => {
  await openWithChat();
  assert.equal(chatCard().querySelector('input[type="checkbox"]').name, 'chat.enabled');
  assert.ok(chatCard().querySelector('textarea[name="chat.prompt"]'));
  assert.equal(chatCard().querySelectorAll('input:disabled').length, 0);
  const model = chatCard().querySelector('select[name="chat.model.google"]'); // the provider in use
  assert.equal(model.value, '');
  assert.deepEqual([...model.options].map((o) => o.value), ['', 'gemini-2.5-flash', 'gemini-2.5-pro']);
  assert.match(chatCard().textContent, /GOOGLE_CHAT_AI_MODEL si está en el \.env/);
  assert.equal(chatCard().querySelector('.adm-warn'), null);
  assert.match(state(), /^Disponible/);
  assert.equal(panel().querySelector('[name="ai.enabled"]'), null); // the notices' AI is not on this page
});

test('the chat is not among the notices that use the AI, and the general AI switch says it is only for them', async () => {
  await open();
  assert.equal(panel().querySelector('[name="chat.enabled"]'), null);
  assert.match(panel().querySelector('[name="ai.enabled"]').closest('label').textContent, /Usar IA en los avisos(?! y el chat)/);
});

test('the chat card says why the players do not have the button', async () => {
  await openWithChat({ ...VALUES, 'chat.enabled': false });
  assert.match(state(), /No disponible: el chat está apagado/);
  await openWithChat(VALUES, { ...CHAT, provider: null, model: null, own_model: false }, providersOf(null, []));
  assert.match(state(), /falta OPENAI_AI_API_KEY o GOOGLE_AI_API_KEY/);
  assert.match(chatCard().querySelector('.adm-warn').textContent, /proveedor y la clave de la IA de los avisos/);
  assert.equal(chatCard().querySelector('select'), null);
  assert.equal(chatCard().querySelector('[data-set-act="test-chat"]').disabled, true);
  await openWithChat(VALUES, { ...CHAT, provider: 'google', model: null, own_model: false });
  assert.match(state(), /falta un modelo \(GOOGLE_AI_MODEL en el \.env, o elígelo aquí\)/);
});

test('switching the chat off is saved like any other switch and touches nothing else', async () => {
  await openWithChat();
  const form = panel().querySelector('#admSettings');
  form.querySelector('[name="chat.enabled"]').checked = false;
  let saved = null;
  installApi({
    'GET /manage/settings': { values: VALUES, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT },
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: ['chat.enabled'], values: VALUES }; },
  });
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(saved.values, { 'chat.enabled': false });
});

test('the chat instructions can be edited and restored to the original ones', async () => {
  await openWithChat(VALUES, { ...CHAT, customized: true });
  const form = panel().querySelector('#admSettings');
  assert.equal(chatCard().querySelector('.adm-tag').textContent, 'Personalizado');
  form.querySelector('[data-set-act="reset-prompt"][data-use="chat"]').click();
  assert.equal(form.elements['chat.prompt'].value, 'd');
  let saved = null;
  installApi({
    'GET /manage/settings': { values: VALUES, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT },
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: ['chat.prompt'], values: VALUES }; },
  });
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(saved.values, { 'chat.prompt': null }); // back to following the application's prompt
});

test('the test button asks the API, which uses what is stored', async () => {
  await openWithChat();
  const calls = installApi({ 'POST /manage/settings/test-chat': { message: 'ok', reply: 'Hola', provider: 'openai', model: 'gpt-chat' } });
  chatCard().querySelector('[data-set-act="test-chat"]').click();
  await settle();
  assert.deepEqual(calls.map((c) => `${c.method} ${c.path}`), ['POST /manage/settings/test-chat']);
});

const LIMIT_FIELDS = ['chat.limit_user_minute', 'chat.limit_user_hour', 'chat.limit_user_day', 'chat.limit_group_minute', 'chat.limit_group_day'];

test('the limits of questions are together, those of the chat and those of the guide, with what the server has', async () => {
  await openLimits();
  const fields = LIMIT_FIELDS.map((name) => limitsCard().querySelector(`input[name="${name}"]`));
  assert.ok(fields.every((field) => field && field.type === 'number' && field.min === '0'));
  assert.deepEqual(fields.map((field) => field.value), ['5', '30', '100', '10', '300']);
  assert.match(limitsCard().textContent, /0 es sin límite/);
  assert.deepEqual([...limitsCard().querySelectorAll('.adm-limit-group')].map((g) => g.textContent), ['Chat', 'Guía de juego']);
  assert.deepEqual([...limitsCard().querySelectorAll('.adm-guide-limits input')].map((i) => i.name), ['guide.limit_user_hour', 'guide.limit_user_day', 'guide.limit_group_day']);
});

test('the card of the chat and that of the guide no longer carry limits nor the choice of who takes the cost', async () => {
  await openLimits(VALUES, ['chat', 'guide']);
  assert.equal(panel().querySelector('input[name^="chat.limit_"]'), null);
  assert.equal(panel().querySelector('input[name^="guide.limit_"]'), null);
  assert.equal(panel().querySelector('select[name$=".key_source"]'), null);
});

test('changing a limit sends that number, and only that one', async () => {
  await openLimits();
  const form = panel().querySelector('#admSettings');
  form.elements['chat.limit_user_day'].value = '0';
  form.elements['chat.limit_group_minute'].value = '20';
  let saved = null;
  installApi({
    'GET /manage/settings': answer(VALUES, GOOGLE, CHAT),
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: [], values: VALUES }; },
  });
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(Object.fromEntries(Object.entries(saved.values).filter(([key]) => key.startsWith('chat.limit_'))), {
    'chat.limit_user_day': 0, 'chat.limit_group_minute': 20, // numbers, not texts, and zero is a value
  });
});

test('the chat model is its own only when picked; the card says what applies otherwise', async () => {
  await openWithChat();
  assert.match(chatCard().textContent, /si no, el modelo de los avisos|y, si no, el modelo de los avisos/);
});

const GUIDE = { provider: 'openai', model: 'gpt-chat', own_model: true, default_prompt: 'g', customized: false };
const openWithGuide = async (values = VALUES, guide = GUIDE) => {
  installApi({ 'GET /manage/settings/ai-models': MODEL_LIST, 'GET /manage/settings': { values: { ...values, 'guide.enabled': true, 'guide.prompt': 'g', 'guide.limit_user_hour': 10, 'guide.limit_user_day': 30, 'guide.limit_group_day': 100, ...values }, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, ai_providers: providersOf(), chat: CHAT, guide } });
  await render(panel(), { entity: { sections: ['guide'] } });
  await settle();
  await settle(); // the list of models is asked after the page is drawn
};
const guideCard = () => panel().querySelector('.adm-guide-card');

test('the guide card has its switch and its instructions, and offers the test; its limits are with the others', async () => {
  await openWithGuide();
  assert.equal(guideCard().querySelector('input[type="checkbox"]').name, 'guide.enabled');
  assert.equal(guideCard().querySelector('input[type="number"]'), null);
  assert.ok(guideCard().querySelector('textarea[name="guide.prompt"]'));
  assert.match(guideCard().querySelector('.adm-guide-state').textContent, /^Disponible/);
  assert.equal(guideCard().querySelector('[data-set-act="test-guide"]').disabled, false);
});

test('the guide card says why the players do not have it', async () => {
  await openWithGuide({ ...VALUES, 'guide.enabled': false });
  assert.match(guideCard().querySelector('.adm-guide-state').textContent, /No disponible: la guía está apagada/);
  await openWithGuide(VALUES, { ...GUIDE, provider: null, model: null });
  assert.match(guideCard().querySelector('.adm-guide-state').textContent, /falta OPENAI_AI_API_KEY o GOOGLE_AI_API_KEY/);
  assert.equal(guideCard().querySelector('[data-set-act="test-guide"]').disabled, true);
});

test('the AI cost card has the price refresh and the retention of the record', async () => {
  installApi({ 'GET /manage/settings': { values: { ...VALUES, 'ai.price_refresh_hours': 24, 'ai.usage_retention_days': 0, 'ai.group_budget_month': 20, 'ai.user_budget_month': 5 }, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT } });
  await render(panel(), { entity: { sections: ['aicost'] } });
  await settle();
  const card = panel().querySelector('.adm-aicost-card');
  assert.deepEqual([...card.querySelectorAll('input[type="number"]')].map((i) => [i.name, i.value]), [
    ['ai.price_refresh_hours', '24'], ['ai.usage_retention_days', '0'],
  ]);
  assert.match(card.textContent, /sin guardar el texto/);
});

test('whose key takes the cost of the chat and of the guide is chosen in the limits, and saved like any other setting', async () => {
  const values = { ...VALUES, 'chat.key_source': 'group_then_user', 'guide.key_source': 'user_only', 'guide.enabled': true, 'guide.prompt': 'g' };
  installApi({ 'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT, guide: CHAT } });
  await render(panel(), { entity: { sections: ['ailimitkeys'] } });
  await settle();
  assert.equal(panel().querySelector('.adm-ailimitkeys-card h3').textContent, 'Quién asume el coste');
  const chat = panel().querySelector('select[name="chat.key_source"]');
  const guide = panel().querySelector('select[name="guide.key_source"]');
  assert.deepEqual([...chat.options].map((o) => o.value), ['user_only', 'group_then_user', 'group_only']);
  assert.equal(chat.value, 'group_then_user');
  assert.equal(guide.value, 'user_only');
  let saved = null;
  installApi({
    'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT, guide: CHAT },
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: Object.keys(body.values), values }; },
  });
  guide.value = 'group_only';
  panel().querySelector('#admSettings').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.deepEqual(saved.values, { 'guide.key_source': 'group_only' });
});

test('the cards of the chat, the guide and the cost explain themselves in the "i" of their title and not in a paragraph under it', async () => {
  const values = { ...VALUES, 'chat.key_source': 'group_then_user', 'guide.key_source': 'user_only', 'guide.enabled': true, 'guide.prompt': 'g', 'ai.price_refresh_hours': 24, 'ai.usage_retention_days': 0, 'ai.group_budget_month': 0, 'ai.user_budget_month': 0 };
  installApi({ 'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT, guide: CHAT } });
  await render(panel(), { entity: { sections: ['chat', 'aicost', 'guide'] } });
  await settle();
  const heads = [...panel().querySelectorAll('.adm-set-card > .pf-info-title')];
  assert.deepEqual(heads.map((h) => h.querySelector('h3').textContent), ['Chat', 'Coste de la IA', 'Guía de juego']);
  assert.match(heads[0].querySelector('.pf-info-text').textContent, /botón flotante.*responde solo sobre videojuegos/);
  assert.match(heads[2].querySelector('.pf-info-text').textContent, /buscando en la web/);
  for (const head of heads) assert.equal(head.nextElementSibling.classList.contains('adm-sub') && head.nextElementSibling.textContent.length > 250, false, 'no long paragraph right under the title');
});

test('everything that limits the AI is in one page: who takes the cost, the question limits, the money budget and the players\' table', async () => {
  const values = { ...VALUES, 'chat.key_source': 'group_then_user', 'guide.key_source': 'user_only', 'ai.group_budget_month': 20, 'ai.user_budget_month': 5 };
  installApi({
    'GET /manage/ai-usage/budgets': { month: '2026-11', resets_on: '2026-12-01', group: { cap: 20, spent: 3 }, default_user_cap: 5, unpriced: { calls: 0, models: [] }, players: [{ user_id: 1, name: 'Ana', is_active: true, override: null, cap: 5, spent: 1, calls: 2 }] },
    'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT, guide: CHAT },
  });
  const { ENTITIES } = await import('../js/pages/admin/entities.js');
  await render(panel(), { entity: ENTITIES.ailimits });
  await settle();
  await settle();
  const titles = [...panel().querySelectorAll('.adm-set-card h3, .adm-budgets-card h3')].map((h) => h.textContent);
  assert.deepEqual(titles, ['Quién asume el coste', 'Límites de preguntas', 'Presupuesto mensual (dinero)', 'Presupuesto de la clave del grupo', 'Tope por jugador']);
  const card = panel().querySelector('.adm-aibudget-card');
  assert.deepEqual([...card.querySelectorAll('input[type="number"]')].map((i) => [i.name, i.value]), [['ai.group_budget_month', '20'], ['ai.user_budget_month', '5']]);
  assert.match(card.textContent, /límite de dinero, distinto de los límites de preguntas/);
  assert.match(card.textContent, /80 % y al 100 % del total del grupo/, 'it says the admins are warned');
  assert.equal(panel().querySelector('tr[data-user="1"] [name="cap"]').value, '');
});

test('Enter in the cap of a player saves that cap and does not submit the settings of the page', async () => {
  const values = { ...VALUES, 'ai.group_budget_month': 20, 'ai.user_budget_month': 5 };
  const sent = [];
  installApi({
    'PUT /manage/ai-usage/budgets/1': ({ body }) => { sent.push(body); return {}; },
    'GET /manage/ai-usage/budgets': { month: '2026-11', resets_on: '2026-12-01', group: { cap: 20, spent: 3 }, default_user_cap: 5, unpriced: { calls: 0, models: [] }, players: [{ user_id: 1, name: 'Ana', is_active: true, override: null, cap: 5, spent: 1, calls: 2 }] },
    'PUT /manage/settings': () => { sent.push('SETTINGS'); return { changed: [], values }; },
    'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat: CHAT, guide: CHAT },
  });
  await render(panel(), { entity: { sections: ['aibudget', 'aibudgets'] } });
  await settle();
  await settle();
  const input = panel().querySelector('tr[data-user="1"] [name="cap"]');
  input.value = '7';
  const enter = new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
  input.dispatchEvent(enter);
  await settle();
  await settle();
  assert.equal(enter.defaultPrevented, true);
  assert.deepEqual(sent, [{ usd: 7 }]);
});
