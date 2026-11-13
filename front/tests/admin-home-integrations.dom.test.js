import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installDom, installStorage } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { integrations } = await import('../js/pages/admin/home.js');

const set = { is_set: true };
const config = (aiModel, enabled = true) => ({
  values: { 'telegram.token': set, 'telegram.group_id': set, 'notifications.enabled': true, 'ai.enabled': enabled, 'push.enabled': false },
  ai_model: aiModel, push_devices: { devices: 0 }, games_sources: { igdb: true }, mail: { configured: false },
});
const aiCard = (cfg) => integrations(cfg).find((card) => card.name === 'Inteligencia artificial').state;

test('the AI card does not need the old single key setting: it reads what the API says is in use', () => {
  assert.deepEqual(aiCard(config({ provider: 'google', model: 'gemini-x' })).slice(0, 2), ['green', 'Activa']);
});

test('the AI card says whether the key or the model is missing', () => {
  assert.deepEqual(aiCard(config({ provider: null, model: null })).slice(0, 2), ['orange', 'Sin clave']);
  assert.match(aiCard(config({ provider: null, model: null }))[2], /OPENAI_AI_API_KEY, GOOGLE_AI_API_KEY o ANTHROPIC_AI_API_KEY/);
  assert.deepEqual(aiCard(config({ provider: 'openai', model: null })).slice(0, 2), ['orange', 'Incompleta']);
  assert.deepEqual(aiCard(config({ provider: null, model: null }, false)).slice(0, 2), ['gray', 'Apagada']);
});
