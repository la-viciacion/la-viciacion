import assert from 'node:assert/strict';
import { afterEach, mock, test } from 'node:test';
import { closeAllModals } from '../js/ui/modal.js';
import { installApi, installDom, installStorage, json, settle } from './dom.js';

installStorage();
installDom('<main id="main"></main>');
const { hltbSyncFlow, scopeOf } = await import('../js/pages/admin/hltb-sync.js');

afterEach(() => {
  closeAllModals();
  mock.timers.reset();
});

const IDLE = { state: 'idle' };
const RUNNING = { state: 'running', processed: 0, total: 5, current: null, updated: 0, unchanged: 0, ambiguous: [], not_found: [], no_time: [], errors: [], stop_reason: null };

async function open(extra = {}) {
  const estimates = [];
  const calls = installApi({
    'GET /manage/hltb-sync/status': () => (calls.some((c) => c.method === 'POST') ? RUNNING : IDLE),
    'GET /manage/hltb-sync/estimate': ({ path }) => {
      estimates.push(path);
      const params = new URLSearchParams(path.split('?')[1]);
      const total = { all: 512, missing: 233, suspicious: 52, recent: Number(params.get('limit')) }[params.get('scope')];
      return { total_games: total, estimated_seconds: total * 6 };
    },
    'POST /manage/hltb-sync/start': RUNNING,
    ...extra,
  });
  await hltbSyncFlow({ onDone: () => {} });
  await settle();
  return { calls, estimates, form: document.querySelector('.modal-content form') };
}

const choose = async (form, scope) => {
  form.elements.scope.value = scope;
  form.elements.scope.dispatchEvent(new window.Event('change'));
  await settle();
};

test('it opens on every game, with how many and how long, and asks for the phrase', async () => {
  const { form, estimates } = await open();
  assert.deepEqual([...form.elements.scope.options].map((o) => o.value), ['all', 'missing', 'suspicious', 'recent']);
  assert.equal(form.elements.scope.value, 'all');
  assert.match(document.querySelector('#hlEstimate').textContent, /512/);
  assert.match(document.querySelector('#hlEstimate').textContent, /52/); // 512 * 6 s = 51,2 min -> 52
  assert.equal(form.querySelector('button[type=submit]').disabled, true);
  assert.deepEqual(estimates, ['/manage/hltb-sync/estimate?scope=all']);
  assert.match(document.querySelector('#hlWarn').textContent, /Pisa los tiempos que ya hay/);
});

test('the figures and the warning follow the choice, and the number of games shows only for the recent ones', async () => {
  const { form, estimates } = await open();
  assert.equal(form.querySelector('[data-for="recent"]').hidden, true);
  await choose(form, 'missing');
  assert.match(document.querySelector('#hlEstimate').textContent, /233/);
  assert.match(document.querySelector('#hlWarn').textContent, /no pisa ninguno/);
  await choose(form, 'recent');
  assert.equal(form.querySelector('[data-for="recent"]').hidden, false);
  assert.equal(estimates.at(-1), '/manage/hltb-sync/estimate?scope=recent&limit=50');
  form.elements.limit.value = '20';
  form.elements.limit.dispatchEvent(new window.Event('change'));
  await settle();
  assert.equal(estimates.at(-1), '/manage/hltb-sync/estimate?scope=recent&limit=20');
  assert.match(document.querySelector('#hlEstimate').textContent, /20/);
});

test('a number of games that makes no sense stops the launch', async () => {
  const { form } = await open();
  await choose(form, 'recent');
  form.elements.limit.value = '0';
  form.elements.limit.dispatchEvent(new window.Event('change'));
  await settle();
  assert.match(document.querySelector('.adm-error').textContent, /entero de 1 en adelante/);
  form.elements.phrase.value = 'SINCRONIZAR';
  form.elements.phrase.dispatchEvent(new window.Event('input'));
  assert.equal(form.querySelector('button[type=submit]').disabled, true);
});

test('the launch sends the phrase and what was chosen', async () => {
  const { form, calls } = await open();
  await choose(form, 'suspicious');
  form.elements.phrase.value = 'SINCRONIZAR';
  form.elements.phrase.dispatchEvent(new window.Event('input'));
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body, { confirm: 'SINCRONIZAR', scope: 'suspicious' });
});

test('the recent ones send their number', async () => {
  const { form, calls } = await open();
  await choose(form, 'recent');
  form.elements.limit.value = '30';
  form.elements.phrase.value = 'SINCRONIZAR';
  form.elements.phrase.dispatchEvent(new window.Event('input'));
  form.requestSubmit();
  await settle();
  assert.deepEqual(calls.find((c) => c.method === 'POST').body, { confirm: 'SINCRONIZAR', scope: 'recent', limit: 30 });
});

test('an error of the API stays in the form', async () => {
  const { form } = await open({ 'POST /manage/hltb-sync/start': json({ detail: 'Ya hay una sincronización en curso' }, 409) });
  form.elements.phrase.value = 'SINCRONIZAR';
  form.elements.phrase.dispatchEvent(new window.Event('input'));
  form.requestSubmit();
  await settle();
  assert.match(document.querySelector('.adm-error').textContent, /Ya hay una sincronización en curso/);
});

test('what the form asks for is read as the API takes it', () => {
  assert.deepEqual(scopeOf('all', '9'), { scope: 'all' });
  assert.deepEqual(scopeOf('recent', '25'), { scope: 'recent', limit: 25 });
  for (const bad of ['', '0', '-3', '2.5', 'x']) assert.equal(scopeOf('recent', bad), null, bad);
});
