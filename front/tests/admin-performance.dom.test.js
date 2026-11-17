import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { render } = await import('../js/pages/admin/performance.js');

const plain = (text) => text.replace(/\s+/g, ' ');
const panel = () => document.getElementById('panel');

const DATA = {
  configured: true,
  window: '24h',
  has_data: true,
  now: { requests: 1234, errors: 3, p50: 0.03, p95: 0.4, in_flight: 1, memory: 300 * 1024 * 1024 },
  charts: {
    requests: [[1000, 1], [1300, 3]],
    errors: [[1000, 0], [1300, 0.5]],
    p95: [[1000, 0.1], [1300, 0.4]],
    memory: [[1000, 3e8], [1300, 3.1e8]],
  },
  routes: {
    slowest: [{ method: 'POST', route: '/api/v1/timers/start', requests: 19, p95: 8.7, errors: 0 }],
    busiest: [{ method: 'GET', route: '/api/v1/timers/now-playing', requests: 1176, p95: 0.07, errors: 2 }],
  },
};

test('without Prometheus it says what is needed and shows nothing else', async () => {
  installApi({ 'GET /manage/performance': { configured: false } });
  await render(panel());
  await settle();
  assert.match(panel().textContent, /Prometheus/);
  assert.equal(panel().querySelector('.adm-stat'), null);
});

test('it shows the figures, four charts and the tables of the slowest and busiest routes', async () => {
  const calls = installApi({ 'GET /manage/performance': DATA });
  await render(panel());
  await settle();
  assert.deepEqual(calls.map((c) => c.path), ['/manage/performance?range=24h']);
  const tiles = [...panel().querySelectorAll('.adm-stat')].map((t) => plain(t.textContent));
  assert.match(tiles[0], /1234Peticiones/);
  assert.match(tiles[2], /400 msTiempo p95/);
  assert.match(tiles[3], /3 \(0,24 %\)/);
  assert.equal(panel().querySelectorAll('svg.sv-chart').length, 4);
  const [slowest, busiest] = [...panel().querySelectorAll('tbody')].map((t) => plain(t.textContent));
  assert.match(slowest, /POST \/timers\/start.*19.*8,70 s/);
  assert.match(busiest, /GET \/timers\/now-playing.*1176.*70 ms.*2/);
});

test('a window without data says so instead of showing an empty page', async () => {
  installApi({ 'GET /manage/performance': { ...DATA, has_data: false, now: { ...DATA.now, requests: null, p50: null, p95: null, errors: 0 }, charts: { requests: [], errors: [], p95: [], memory: [] }, routes: { slowest: [], busiest: [] } } });
  await render(panel());
  await settle();
  assert.match(panel().textContent, /Prometheus aún no tiene peticiones/);
  assert.equal(panel().querySelectorAll('.pf-sub').length >= 1, true);
  assert.match(plain(panel().textContent), /Aún no hay rutas con peticiones suficientes/);
});

test('choosing another period asks for it, and Actualizar asks again for fresh data', async () => {
  const calls = installApi({ 'GET /manage/performance': DATA });
  await render(panel());
  await settle();
  panel().querySelector('[data-window="7d"]').click();
  await settle();
  panel().querySelector('#perfRefresh').click();
  await settle();
  assert.deepEqual(calls.map((c) => c.path), ['/manage/performance?range=24h', '/manage/performance?range=7d', '/manage/performance?range=7d&refresh=true']);
  assert.equal(panel().querySelector('[data-window="7d"]').getAttribute('aria-pressed'), 'true');
});

test('a failure of the API shows the message', async () => {
  installApi({ 'GET /manage/performance': () => new Response(JSON.stringify({ detail: 'Prometheus no responde' }), { status: 502, headers: { 'Content-Type': 'application/json' } }) });
  await render(panel());
  await settle();
  assert.match(panel().textContent, /Prometheus no responde/);
});

test('an answer that arrives after the admin left the tab is not painted over the new one', async () => {
  let answer;
  installApi({ 'GET /manage/performance': () => new Promise((resolve) => { answer = resolve; }) });
  const pending = render(panel());
  panel().innerHTML = '<p id="other">Otra pestaña</p>'; // the admin moved on
  answer(new Response(JSON.stringify(DATA), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  await pending;
  await settle();
  assert.equal(panel().textContent, 'Otra pestaña');
});
