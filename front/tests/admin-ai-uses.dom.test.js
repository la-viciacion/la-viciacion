import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { render } = await import('../js/pages/admin/settings.js');

const VALUES = {
  'ai.enabled': true, 'ai.provider': { is_set: true }, 'ai.api_key': { is_set: true }, 'ai.model': { is_set: true },
  'ai.use.completed_game': true, 'ai.use.new_game': false, 'chat.enabled': true, 'chat.model': { is_set: true }, 'chat.prompt': 'd',
  'chat.limit_user_minute': 5, 'chat.limit_user_hour': 30, 'chat.limit_user_day': 100, 'chat.limit_group_minute': 10, 'chat.limit_group_day': 300, 'completed_game.recommend': true,
  'telegram.token': { is_set: false }, 'telegram.group_id': { is_set: false }, 'telegram.admin_chat_id': { is_set: false }, 'push.vapid_private': { is_set: true },
  'ai.prompt.completed_game': 'a', 'ai.prompt.completed_game_recommendation': 'b', 'ai.prompt.new_game': 'c',
};
const CHAT = { provider: 'openai', model: 'gpt-chat', own_model: true, default_prompt: 'd', customized: false };
const USES = [
  { id: 'new_game', label: 'Empieza un juego', help: 'h1', switchable: true, switch: 'ai.use.new_game', parent: null, default_prompt: 'c', customized: false },
  { id: 'completed_game', label: 'Completa un juego', help: 'h2', switchable: true, switch: 'ai.use.completed_game', parent: null, default_prompt: 'a', customized: true },
  { id: 'completed_game_recommendation', label: 'Recomendación al completar', help: 'h3', switchable: false, switch: 'completed_game.recommend', parent: 'completed_game', default_prompt: 'b', customized: true },
];

const panel = () => document.getElementById('panel');
const open = async (values = VALUES, model = 'gemini-test') => {
  installApi({ 'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model }, chat: CHAT } });
  await render(panel(), { entity: { sections: ['ai', 'aiuses'] } });
  await settle();
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

const answer = (values, aiModel, chat) => ({ values, jobs: {}, push_devices: { devices: 2, users: 1 }, mail: { configured: false, missing: [], test_recipient: null }, ai_uses: USES, ai_model: aiModel, chat });
const GOOGLE = { provider: 'google', model: 'gemini-test' };
const openSections = async (sections, values = VALUES, aiModel = GOOGLE, chat = CHAT) => {
  installApi({ 'GET /manage/settings': answer(values, aiModel, chat) });
  await render(panel(), { entity: { sections } });
  await settle();
};

test('Notificaciones → IA has only the switch, the test and the notices: no provider, key or model', async () => {
  await open();
  assert.equal(panel().querySelector('[name="ai.enabled"]').type, 'checkbox');
  assert.ok(panel().querySelector('[data-set-act="test-ai"]'));
  assert.equal(panel().querySelector('.adm-ai-provider'), null);
  assert.equal(panel().querySelector('.adm-ai-model'), null);
  assert.equal(panel().querySelectorAll('input:disabled').length, 0);
  assert.match(panel().textContent, /Usa Google \(Gemini\) \(gemini-test\)/);
  assert.equal(panel().querySelector('.adm-warn'), null);
});

test('saving the AI switch never sends the provider, the key or the model', async () => {
  await open();
  const form = panel().querySelector('#admSettings');
  form.querySelector('[name="ai.enabled"]').checked = false;
  let saved = null;
  installApi({
    'GET /manage/settings': answer(VALUES, GOOGLE, CHAT),
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: [], values: VALUES }; },
  });
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(saved.values['ai.enabled'], false);
  assert.deepEqual(Object.keys(saved.values).filter((key) => /provider|api_key|model/.test(key)), []);
});

test('Sistema → Servicios shows the AI provider, key and models read only, the chat one apart', async () => {
  await openSections(['aiconfig']);
  assert.equal(panel().querySelector('.adm-ai-provider').value, 'Google (Gemini)');
  assert.equal(panel().querySelector('.adm-ai-model').value, 'gemini-test');
  assert.equal(panel().querySelector('.adm-chat-model').value, 'gpt-chat');
  assert.equal(panel().querySelectorAll('input:disabled').length, 4);
  assert.equal(panel().querySelector('select[name="ai.provider"]'), null);
  assert.equal(panel().querySelector('.adm-warn'), null);
  assert.match(panel().textContent, /CHAT_AI_MODEL si está en el \.env/);
  assert.doesNotMatch(panel().textContent, /ahora no lo está/);
});

test('without a model of its own the chat says it uses AI_MODEL', async () => {
  await openSections(['aiconfig'], VALUES, GOOGLE, { ...CHAT, model: 'gemini-test', own_model: false });
  assert.equal(panel().querySelector('.adm-chat-model').value, 'gemini-test');
  assert.match(panel().textContent, /ahora no lo está: usa AI_MODEL/);
});

test('without AI_MODEL or AI_PROVIDER both pages say the AI writes nothing and which one is missing', async () => {
  await openSections(['aiconfig'], VALUES, { provider: 'google', model: null });
  assert.equal(panel().querySelector('.adm-ai-model').value, 'Sin configurar');
  assert.match(panel().querySelector('.adm-warn').textContent, /Falta AI_MODEL en el \.env/);
  await openSections(['aiconfig'], VALUES, { provider: null, model: null });
  assert.equal(panel().querySelector('.adm-ai-provider').value, 'Sin configurar');
  assert.match(panel().querySelector('.adm-warn').textContent, /Falta AI_PROVIDER, AI_MODEL en el \.env/);
  await openSections(['ai', 'aiuses'], VALUES, { provider: null, model: null });
  assert.match(panel().querySelector('.adm-warn').textContent, /Falta AI_PROVIDER, AI_MODEL en el \.env/);
});

test('Servicios also holds Telegram, the push contact and keys and the mail, and Canales keeps only the sending', async () => {
  await openSections(['aiconfig', 'telegramconfig', 'pushconfig', 'mail']);
  assert.equal(panel().querySelectorAll('.adm-set-card').length, 4);
  assert.equal(panel().querySelectorAll('input[disabled]').length >= 7, true); // AI x4, Telegram x3
  assert.ok(panel().querySelector('[name="push.contact"]'));
  assert.ok(panel().querySelector('[data-set-act="push-keys"]'));
  assert.ok(panel().querySelector('[data-set-act="test-email"]'));
  assert.equal(panel().querySelector('[data-set-act="test"]'), null);
  await openSections(['telegram', 'push']);
  assert.equal(panel().querySelectorAll('input[disabled]').length, 0);
  assert.equal(panel().querySelector('[name="push.contact"]'), null);
  assert.equal(panel().querySelector('[data-set-act="push-keys"]'), null);
  assert.equal(panel().querySelector('[name="push.enabled"]').type, 'checkbox');
  assert.ok(panel().querySelector('[data-set-act="test"]'));
});

test('Canales says whether Telegram is set and only allows the test when it is', async () => {
  await openSections(['telegram']);
  assert.match(panel().querySelector('.adm-warn').textContent, /faltan TELEGRAM_TOKEN y TELEGRAM_GROUP_ID/);
  assert.equal(panel().querySelector('[data-set-act="test"]').disabled, true);
  await openSections(['telegram'], { ...VALUES, 'telegram.token': { is_set: true }, 'telegram.group_id': { is_set: true } });
  assert.equal(panel().querySelector('.adm-warn'), null);
  assert.equal(panel().querySelector('[data-set-act="test"]').disabled, false);
});

const openWithChat = async (values = VALUES, chat = CHAT) => {
  installApi({ 'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' }, chat } });
  await render(panel(), { entity: { sections: ['chat'] } });
  await settle();
};
const chatCard = () => panel().querySelector('.adm-chat-card');
const state = () => chatCard().querySelector('.adm-chat-state').textContent;

test('the chat card shows its switch and its instructions, and where its model comes from', async () => {
  await openWithChat();
  assert.equal(chatCard().querySelector('input[type="checkbox"]').name, 'chat.enabled');
  assert.ok(chatCard().querySelector('textarea[name="chat.prompt"]'));
  assert.equal(chatCard().querySelectorAll('input:disabled').length, 0); // what comes from the .env is in Servicios
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
  await openWithChat({ ...VALUES, 'ai.api_key': { is_set: false } }, { ...CHAT, provider: null, model: null, own_model: false });
  assert.match(state(), /falta AI_PROVIDER, AI_API_KEY, AI_MODEL \(o CHAT_AI_MODEL\) en el \.env/);
  assert.match(chatCard().querySelector('.adm-warn').textContent, /proveedor y la clave de la IA de los avisos/);
  assert.equal(chatCard().querySelector('[data-set-act="test-chat"]').disabled, true);
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

test('the chat card has the limits per player and for the group, with what the server has', async () => {
  await openWithChat();
  const fields = LIMIT_FIELDS.map((name) => chatCard().querySelector(`input[name="${name}"]`));
  assert.ok(fields.every((field) => field && field.type === 'number' && field.min === '0'));
  assert.deepEqual(fields.map((field) => field.value), ['5', '30', '100', '10', '300']);
  assert.match(chatCard().textContent, /0 es sin límite/);
});

test('changing a limit sends that number, and only that one', async () => {
  await openWithChat();
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
