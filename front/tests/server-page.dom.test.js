import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
globalThis.location = window.location;
const server = await import('../js/pages/server/index.js');

const line = (base) => [[1000, base], [1300, base * 2], [1600, base]];
const COST = {
  currency: 'EUR', month: { so_far: 2.3, projected: 5.88 }, year: { so_far: 40.5, projected: 44.1 }, total: { so_far: 120.25, since: '2023-12-05' },
};
const STATUS = {
  configured: true, window: '24h', step: 300, fetched_at: '2026-10-11T10:00:00+00:00',
  server: {
    name: 'lavi <b>', status: 'running', created: '2026-01-10T08:00:00+00:00', type: 'cx22', cores: 2, memory_gb: 4, disk_gb: 40,
    location: 'Falkenstein, DE', traffic: { in: 1_000_000, out: 5_000_000_000_000, included: 20_000_000_000_000 },
  },
  metrics: { cpu: line(10), net_in: line(1000), net_out: line(2000), disk_read: [], disk_write: line(5) },
  cost: COST,
};
const HOST = {
  memory: { used: 3e9, total: 4e9, series: [[1000, 60], [1300, 75]] },
  disk: { used: 10e9, total: 40e9, series: [[1000, 25], [1300, 25]] },
  load: [0.5, 0.4, 0.3], cores: 2, uptime: 90061,
};

const main = () => document.getElementById('main');

test('everybody sees the state, the charts, the traffic and the cost, escaped', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  assert.equal(text('.sv-name')[0], 'lavi <b>');
  assert.equal(document.querySelectorAll('.sv-name b').length, 0);
  assert.equal(text('.sv-status')[0], 'En marcha');
  assert.match(text('.sv-head .pf-sub')[0], /cx22 · 2 vCPU · 4 GB RAM · 40 GB de disco · Falkenstein, DE/);
  assert.equal(document.querySelectorAll('.sv-title').length, 5);
  assert.equal(document.querySelectorAll('.sv-line').length, 5);
  assert.equal(document.querySelector('.sv-line.cpu').getAttribute('points').split(' ').length, 3);
  assert.equal(document.querySelectorAll('.sv-line[points=""]').length, 1); // no read of the disk: nothing to draw
  assert.match(main().textContent, /Salida 5 TB de 20 TB incluidos/);
  assert.equal(document.querySelector('.sv-meter').getAttribute('aria-valuenow'), '25');
  assert.match(document.querySelector('[aria-label="Gasto estimado"]').textContent, /2,30\s€/);
});

test('the cost shows the month, the year and the total since the start, with what is forecast', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  const card = document.querySelector('[aria-label="Gasto estimado"]');
  const rows = text('tbody tr', card).map((t) => t.replace(/\s/g, ' '));
  assert.deepEqual(rows, ['Este mes2,30 €5,88 €', 'Este año40,50 €44,10 €', 'Desde el inicio (diciembre de 2023)120,25 €—']);
  assert.match(card.textContent, /Es una estimación\./);
  assert.equal(document.querySelector('.sv-months'), null);
});

test('the period buttons sit with the charts and the month\'s traffic and cost come apart from them', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  assert.deepEqual(text('.sv-section-title'), ['Rendimiento', 'Mes en curso']);
  const [charts, month] = document.querySelectorAll('.sv-grid-cards');
  assert.deepEqual(text('.sv-title', charts), ['CPU', 'Red', 'Disco']);
  assert.deepEqual(text('.sv-title', month), ['Tráfico de este mes', 'Gasto estimado']);
  assert.ok(document.querySelector('.sv-section [data-window]'));
  assert.equal(month.querySelector('[data-window]'), null);
});

test('another period asks the API again and marks its button', async () => {
  const calls = installApi({ 'GET /server/status?range=': STATUS });
  await server.render({ main: main() });
  await settle();
  assert.equal(document.querySelector('[data-window="24h"]').getAttribute('aria-pressed'), 'true');
  document.querySelector('[data-window="7d"]').click();
  await settle();
  assert.equal(calls.at(-1).path, '/server/status?range=7d');
  assert.equal(document.querySelector('[data-window="7d"]').getAttribute('aria-pressed'), 'true');
  document.querySelector('[data-window="7d"]').click();
  await settle();
  assert.equal(calls.length, 2); // the one already shown is not asked again
});

test('without a token it says so, and a failure shows what Hetzner said', async () => {
  installApi({ 'GET /server/status': { configured: false } });
  await server.render({ main: main() });
  await settle();
  assert.match(main().textContent, /no está configurado/);
  installApi({ 'GET /server/status': json({ detail: 'Hetzner rechaza el token' }, 502) });
  await server.render({ main: main() });
  await settle();
  assert.match(main().textContent, /Error consultando el servidor: Hetzner rechaza el token/);
});

test('with Prometheus the panel adds memory, disk space and the load of the machine', async () => {
  installApi({ 'GET /server/status?range=24h': { ...STATUS, host: HOST } });
  await server.render({ main: main() });
  await settle();
  const [charts] = document.querySelectorAll('.sv-grid-cards');
  assert.deepEqual(text('.sv-title', charts), ['CPU', 'Memoria', 'Espacio en disco', 'Carga y tiempo encendido', 'Red', 'Disco']);
  const memory = document.querySelector('[aria-label="Memoria"]');
  assert.match(memory.textContent, /Usado\s+75\s%\s+En uso\s+3 GB de 4 GB/);
  assert.match(document.querySelector('[aria-label="Espacio en disco"]').textContent, /Usado\s+25\s%\s+En uso\s+10 GB de 40 GB/);
  const load = document.querySelector('[aria-label="Carga de la máquina"]').textContent;
  assert.match(load, /0,50 · 0,40 · 0,30/);
  assert.match(load, /2 núcleos/);
  assert.match(load, /Encendido desde hace 1 d 1 h/);
});

test('without the address of Prometheus there is nothing of the machine', async () => {
  installApi({ 'GET /server/status?range=24h': { ...STATUS, host: null } });
  await server.render({ main: main() });
  await settle();
  assert.equal(document.querySelector('[aria-label="Memoria"]'), null);
  assert.equal(document.querySelectorAll('.sv-line').length, 5); // the charts of Hetzner are there
});

test('when Prometheus fails the whole panel is an error that says why', async () => {
  installApi({ 'GET /server/status?range=24h': json({ detail: 'Prometheus no responde (ConnectionError)' }, 502) });
  await server.render({ main: main() });
  await settle();
  assert.match(main().textContent, /Error consultando el servidor: Prometheus no responde/);
  assert.equal(document.querySelectorAll('.sv-line').length, 0);
});

test('a part Prometheus has no data for is left out', async () => {
  installApi({ 'GET /server/status?range=24h': { ...STATUS, host: { ...HOST, disk: null, load: null, uptime: null } } });
  await server.render({ main: main() });
  await settle();
  assert.ok(document.querySelector('[aria-label="Memoria"]'));
  assert.equal(document.querySelector('[aria-label="Espacio en disco"]'), null);
  assert.doesNotMatch(document.querySelector('[aria-label="Carga de la máquina"]').textContent, /Encendido|núcleos/);
});
