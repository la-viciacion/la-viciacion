import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { render } = await import('../js/pages/admin/settings.js');

const VALUES = {
  'ai.enabled': true, 'ai.provider': 'google', 'ai.api_key': { is_set: true }, 'ai.model': { is_set: true },
  'ai.use.completed_game': true, 'ai.use.new_game': false, 'completed_game.recommend': true,
  'telegram.token': { is_set: false }, 'telegram.group_id': { is_set: false }, 'telegram.admin_chat_id': { is_set: false }, 'push.vapid_private': { is_set: true },
  'ai.prompt.completed_game': 'a', 'ai.prompt.completed_game_recommendation': 'b', 'ai.prompt.new_game': 'c',
};
const USES = [
  { id: 'new_game', label: 'Empieza un juego', help: 'h1', switchable: true, switch: 'ai.use.new_game', parent: null, default_prompt: 'c', customized: false },
  { id: 'completed_game', label: 'Completa un juego', help: 'h2', switchable: true, switch: 'ai.use.completed_game', parent: null, default_prompt: 'a', customized: true },
  { id: 'completed_game_recommendation', label: 'Recomendación al completar', help: 'h3', switchable: false, switch: 'completed_game.recommend', parent: 'completed_game', default_prompt: 'b', customized: true },
];

const panel = () => document.getElementById('panel');
const open = async (values = VALUES, model = 'gemini-test') => {
  installApi({ 'GET /manage/settings': { values, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model } } });
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

test('the AI card shows the model of the environment, read only, and cannot change it', async () => {
  await open();
  const field = panel().querySelector('.adm-ai-model');
  assert.equal(field.value, 'gemini-test');
  assert.equal(field.disabled, true);
  assert.equal(panel().querySelector('.adm-warn'), null);
  const form = panel().querySelector('#admSettings');
  form.querySelector('[name="ai.enabled"]').checked = false;
  let saved = null;
  installApi({
    'GET /manage/settings': { values: VALUES, jobs: {}, push_devices: { devices: 0, users: 0 }, mail: { configured: false, missing: [] }, ai_uses: USES, ai_model: { provider: 'google', model: 'gemini-test' } },
    'PUT /manage/settings': ({ body }) => { saved = body; return { changed: [], values: VALUES }; },
  });
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(saved.values['ai.enabled'], false);
  assert.equal('ai.model' in saved.values, false); // the model never travels back to the API
});

test('without AI_MODEL the card says the AI writes nothing and where to set it', async () => {
  await open(VALUES, null);
  assert.equal(panel().querySelector('.adm-ai-model').value, 'Sin configurar');
  assert.match(panel().querySelector('.adm-warn').textContent, /Falta AI_MODEL en el \.env/);
});
