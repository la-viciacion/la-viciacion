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
  chat: { available: true, needs_key: false, paid_by: key.has_key ? 'user' : 'group', mode: 'user_or_group' },
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

const el = () => document.getElementById('pfAi');
const open = async (routes) => {
  el().replaceWith(el().cloneNode(false)); // a new element: the listeners of the screen before it go with the old one
  const calls = installApi(routes);
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

test('without a key it explains who pays, offers the key box and loads no models', async () => {
  const calls = await open({ 'GET /users/ana/ai': stateOf(NONE) });
  assert.match(el().textContent, /Lo paga el grupo mientras no guardes tu propia clave/);
  assert.match(el().textContent, /Se paga con tu propia clave: guárdala/);
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
  assert.match(el().textContent, /Se paga con tu clave, de tu cuenta de OpenAI/);
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
