import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installApi, installDom, installStorage, json, settle, text } from './dom.js';

installStorage();
const window = installDom('<main id="main"></main>');
globalThis.location = window.location;
const server = await import('../js/pages/server/index.js');

const line = (base) => [[1000, base], [1300, base * 2], [1600, base]];
const month = (n, year = 2026, running = 10) => {
  const state = year < 2026 || n < running ? 'closed' : n === running ? 'running' : 'future';
  const kinds = state === 'future' ? { server: 0, domain: 0 } : { server: n === running && year === 2026 ? 2 : 4.9, domain: n === running && year === 2026 ? 0.3 : 1 };
  return { month: `${year}-${String(n).padStart(2, '0')}`, state, kinds, forecast: state === 'closed' ? 0 : state === 'running' ? 3.6 : 5.9 };
};
const monthsOf = (year) => Array.from({ length: 12 }, (_, i) => month(i + 1, year));

const COST = {
  currency: 'EUR', month: { so_far: 2.3, projected: 5.88 }, year: { so_far: 40.5, projected: 44.1 }, total: { so_far: 120.25, since: '2023-12-05' },
  kinds: [
    { kind: 'server', month: { so_far: 2, projected: 5.4 }, year: { so_far: 38, projected: 41 }, total: { so_far: 108 } },
    { kind: 'domain', month: { so_far: 0.3, projected: 0.48 }, year: { so_far: 2.5, projected: 3.1 }, total: { so_far: 12.25 } },
  ],
  years: [2025, 2026], months: monthsOf(2026),
};
const STATUS = {
  configured: true, window: '24h', step: 300, fetched_at: '2026-10-11T10:00:00+00:00',
  server: {
    created: '2026-01-10T08:00:00+00:00', type: 'cx22', cores: 2, memory_gb: 4, disk_gb: 40,
    location: 'Falkenstein <b>, DE', traffic: { in: 1_000_000, out: 5_000_000_000_000, included: 20_000_000_000_000 },
  },
  metrics: { cpu: line(10), net_in: line(1000), net_out: line(2000), disk_read: [], disk_write: line(5) },
  cost: COST,
};
const HOST = {
  memory: { used: 3e9, total: 4e9, series: [[1000, 60], [1300, 75]] },
  disk: { used: 10e9, total: 40e9, series: [[1000, 25], [1300, 25]] },
  load: [0.5, 0.4, 0.3], cores: 2, uptime: 90061,
};

test('the page is for everybody: it is not admin-only', () => {
  assert.equal(server.adminOnly, undefined);
});

const main = () => document.getElementById('main');

test('everybody sees the characteristics, the charts, the traffic and the cost, escaped', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  assert.deepEqual(text('.sv-spec dt'), ['Plan', 'CPU', 'Memoria', 'Disco', 'Ubicación']); // each characteristic says what it is
  assert.deepEqual(text('.sv-spec dd'), ['cx22', '2 vCPU', '4 GB', '40 GB', 'Falkenstein <b>, DE']);
  assert.equal(document.querySelectorAll('.sv-head b').length, 0); // escaped
  assert.equal(document.querySelectorAll('.sv-title').length, 6); // CPU, network, disk, traffic, the breakdown and the months
  assert.equal(document.querySelectorAll('.sv-line').length, 5);
  assert.equal(document.querySelector('.sv-line.cpu').getAttribute('points').split(' ').length, 3);
  assert.equal(document.querySelectorAll('.sv-line[points=""]').length, 1); // no read of the disk: nothing to draw
  assert.match(main().textContent, /Salida 5 TB de 20 TB incluidos/);
  assert.equal(document.querySelector('.sv-meter').getAttribute('aria-valuenow'), '25');
  assert.match(document.querySelector('[aria-label="Costes"]').textContent, /2,30\s€/);
});

test('the costs have a section of their own: the month, the year and the whole life with what is forecast', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  const tiles = [...document.querySelectorAll('.sv-tile')].map((t) => t.textContent.replace(/\s+/g, ' ').trim());
  assert.deepEqual(tiles, ['Este mes2,30 €previsto 5,88 €', 'Este año40,50 €previsto 44,10 €', 'Desde el inicio120,25 €desde diciembre de 2023']);
  assert.match(document.querySelector('[aria-label="Desglose de costes"]').textContent, /Es una estimación\./);
});

test('the breakdown gives each kind its month, year and total, and a total row when there are several', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  const card = document.querySelector('[aria-label="Desglose de costes"]');
  const clean = (t) => t.replace(/\s/g, ' ');
  assert.deepEqual(text('thead th', card), ['Concepto', 'Este mes', 'Este año', 'Desde el inicio']);
  assert.deepEqual(text('tbody tr', card).map(clean), ['Servidor2,00 €38,00 €108,00 €', 'Dominio0,30 €2,50 €12,25 €']);
  assert.deepEqual(text('tfoot tr', card).map(clean), ['Total2,30 €40,50 €120,25 €']);
});

test('with a single kind there is no total row, and a kind the page does not know keeps its name', async () => {
  const kinds = [{ kind: 'server', month: { so_far: 2, projected: 5 }, year: { so_far: 38, projected: 41 }, total: { so_far: 108 } }];
  installApi({ 'GET /server/status?range=24h': { ...STATUS, cost: { ...COST, kinds } } });
  await server.render({ main: main() });
  await settle();
  assert.equal(document.querySelector('[aria-label="Desglose de costes"] tfoot'), null);
  installApi({ 'GET /server/status?range=24h': { ...STATUS, cost: { ...COST, kinds: [{ ...kinds[0], kind: 'energia' }] } } });
  await server.render({ main: main() });
  await settle();
  assert.deepEqual(text('[aria-label="Desglose de costes"] tbody th'), ['energia']);
});

test('without any rate yet the page has no costs section', async () => {
  installApi({ 'GET /server/status?range=24h': { ...STATUS, cost: null } });
  await server.render({ main: main() });
  await settle();
  assert.deepEqual(text('.sv-section-title'), ['Rendimiento', 'Tráfico del mes']);
});

test('the period buttons sit with the charts only: the traffic and the costs are sections of their own', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  assert.deepEqual(text('.sv-section-title'), ['Rendimiento', 'Tráfico del mes', 'Costes']);
  const [charts] = document.querySelectorAll('.sv-grid-cards');
  assert.deepEqual(text('.sv-title', charts), ['CPU', 'Red', 'Disco']);
  assert.ok(document.querySelector('.sv-section [data-window]'));
  assert.equal(document.querySelector('[aria-label="Costes"] [data-window]'), null);
  assert.ok(document.querySelector('[aria-label="Tráfico del mes"]'));
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
  assert.equal(calls.filter((c) => c.path.startsWith('/server/status')).length, 2); // the one already shown is not asked again
  assert.equal(calls.filter((c) => c.path === '/server/ai-costs').length, 1); // the AI's spend does not depend on the period: asked once
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

const clean = (t) => t.replace(/\s+/g, ' ').trim();
const year = () => document.querySelector('#svYear');

test('the costs by month: twelve bars of the running year, the running month selected and its detail below', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  assert.deepEqual(text('[data-year]', year()), ['2025', '2026']);
  assert.equal(year().querySelector('[data-year="2026"]').getAttribute('aria-pressed'), 'true');
  assert.deepEqual(text('.sv-bar-label', year()), ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']);
  assert.equal(year().querySelector('[data-month="2026-10"]').getAttribute('aria-pressed'), 'true');
  assert.deepEqual([...year().querySelectorAll('.sv-bar')].map((bar) => bar.classList.contains('future')), [...Array(10).fill(false), true, true]);
  assert.ok([...year().querySelectorAll('.sv-bar')].every((bar) => bar.tagName === 'BUTTON')); // real buttons: the keyboard works
  assert.equal(year().querySelectorAll('.sv-forecast').length, 3); // the rest of October, November and December
  assert.deepEqual(text('.sv-key', year()), ['Servidor', 'Dominio', 'Previsto']);
  assert.match(clean(year().querySelector('.sv-cost-total').textContent), /^\d+,\d\d € en 2026 · \d+,\d\d € previstos a fin de año$/);
  assert.equal(text('.sv-detail-title', year())[0], 'Octubre de 2026');
  assert.deepEqual(text('.sv-detail tbody tr', year()).map(clean), ['Servidor2,00 €', 'Dominio0,30 €', 'Lo que queda previsto3,60 €']);
  assert.deepEqual(text('.sv-detail tfoot tr', year()).map(clean), ['Total previsto5,90 €']);
});

test('pressing a month shows its detail: a closed one is a total, a future one all forecast', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS });
  await server.render({ main: main() });
  await settle();
  year().querySelector('[data-month="2026-03"]').click();
  assert.equal(text('.sv-detail-title', year())[0], 'Marzo de 2026');
  assert.deepEqual(text('.sv-detail tfoot tr', year()).map(clean), ['Total5,90 €']);
  assert.equal(year().querySelector('.sv-detail .sv-pending'), null);
  year().querySelector('[data-month="2026-12"]').click();
  assert.equal(text('.sv-detail-title', year())[0], 'Diciembre de 2026');
  assert.deepEqual(text('.sv-detail tbody tr', year()).map(clean), ['Lo que queda previsto5,90 €']); // nothing spent yet, only forecast
  assert.equal(year().querySelector('[data-month="2026-12"]').getAttribute('aria-pressed'), 'true');
});

test('another year is asked for once, shown whole with no forecast, and the running one comes back without asking again', async () => {
  const calls = installApi({ 'GET /server/status?range=': STATUS, 'GET /server/costs?year=2025': { year: 2025, months: monthsOf(2025) } });
  await server.render({ main: main() });
  await settle();
  year().querySelector('[data-year="2025"]').click();
  await settle();
  assert.equal(year().querySelector('[data-year="2025"]').getAttribute('aria-pressed'), 'true');
  assert.equal(year().querySelectorAll('.sv-forecast').length, 0);
  assert.deepEqual(text('.sv-key', year()), ['Servidor', 'Dominio']); // nothing is forecast in a year that is over
  assert.doesNotMatch(year().querySelector('.sv-cost-total').textContent, /previstos/);
  assert.equal(text('.sv-detail-title', year())[0], 'Diciembre de 2025');
  year().querySelector('[data-year="2026"]').click();
  await settle();
  year().querySelector('[data-year="2025"]').click();
  await settle();
  assert.equal(calls.filter((c) => c.path === '/server/costs?year=2025').length, 1);
  assert.equal(calls.filter((c) => c.path.startsWith('/server/status')).length, 1);
});

test('a year that cannot be read says so and the page stays on the one it had', async () => {
  installApi({ 'GET /server/status?range=': STATUS, 'GET /server/costs?year=2025': json({ detail: 'Ese año no tiene gastos registrados' }, 404) });
  await server.render({ main: main() });
  await settle();
  year().querySelector('[data-year="2025"]').click();
  await settle();
  assert.match(year().textContent, /Error consultando los costes de 2025: Ese año no tiene gastos registrados/);
  assert.equal(year().querySelector('[data-year="2026"]').getAttribute('aria-pressed'), 'true');
});

test('changing the period of the charts keeps the year and the month being looked at', async () => {
  installApi({ 'GET /server/status?range=': STATUS, 'GET /server/costs?year=2025': { year: 2025, months: monthsOf(2025) } });
  await server.render({ main: main() });
  await settle();
  year().querySelector('[data-year="2025"]').click();
  await settle();
  year().querySelector('[data-month="2025-04"]').click();
  document.querySelector('[data-window="7d"]').click();
  await settle();
  assert.equal(year().querySelector('[data-year="2025"]').getAttribute('aria-pressed'), 'true');
  assert.equal(text('.sv-detail-title', year())[0], 'Abril de 2025');
});

const card = (name) => document.querySelector(`[aria-label="${name}"]`);

test('every chart has its vertical axis and the time at both ends', async () => {
  installApi({ 'GET /server/status?range=24h': { ...STATUS, host: HOST } });
  await server.render({ main: main() });
  await settle();
  assert.deepEqual(text('.sv-yaxis span', card('CPU')), ['100 %', '50 %', '0 %']);
  assert.deepEqual(text('.sv-yaxis span', card('Memoria')), ['100 %', '50 %', '0 %']);
  assert.deepEqual(text('.sv-yaxis span', card('Red')), ['4 KB/s', '2 KB/s', '0 B/s']); // the highest of both series
  assert.deepEqual(text('.sv-yaxis span', card('Disco')), ['10 B/s', '5 B/s', '0 B/s']);
  for (const name of ['CPU', 'Memoria', 'Espacio en disco', 'Red', 'Disco']) {
    const [from, now] = text('.sv-xaxis span', card(name));
    assert.match(from, /^\d\d:\d\d$/, name);
    assert.equal(now, 'ahora', name);
  }
});

test('the CPU, the memory and the disk space have a dotted line at the recommended maximum, the network and the disk I/O do not', async () => {
  installApi({ 'GET /server/status?range=24h': { ...STATUS, host: HOST } });
  await server.render({ main: main() });
  await settle();
  const y = (name) => card(name).querySelector('.sv-limit')?.getAttribute('y1');
  assert.equal(y('CPU'), '16.0'); // 80 % of an 80 high box, counted from the bottom
  assert.equal(y('Memoria'), '12.0'); // 85 %
  assert.equal(y('Espacio en disco'), '12.0');
  assert.equal(y('Red'), undefined);
  assert.equal(y('Disco'), undefined);
  assert.match(text('.sv-legend', card('CPU'))[0].replace(/\s+/g, ' '), /Máximo recomendado 80\s%/);
  assert.doesNotMatch(card('Red').textContent, /recomendado/);
});

test('with the period of seven days the axis names days', async () => {
  installApi({ 'GET /server/status?range=': STATUS });
  await server.render({ main: main() });
  await settle();
  document.querySelector('[data-window="7d"]').click();
  await settle();
  assert.match(text('.sv-xaxis span', card('CPU'))[0], /^\d{1,2} \p{L}+/u);
});

const AI = {
  currency: 'usd', source: 'billed', month: 0.5, year: 1.75, total: 5.75, since: '2025-12',
  months: [{ month: '2025-12', total: 4 }, { month: '2026-10', total: 1.25 }, { month: '2026-11', total: 0.5 }],
};

test('the AI has its own block in dollars, apart from the euro costs, and is never converted', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS, 'GET /server/ai-costs': AI });
  await server.render({ main: main() });
  await settle();
  const block = document.querySelector('[aria-label="Gasto en IA"]');
  assert.match(block.textContent, /0,50\sUS\$/);
  assert.match(block.textContent, /1,75\sUS\$/);
  assert.match(block.textContent, /5,75\sUS\$.*desde diciembre de 2025/);
  assert.doesNotMatch(block.textContent, /€/);
  const months = document.querySelector('[aria-label="Gasto en IA mes a mes"]');
  assert.deepEqual([...months.querySelectorAll('tbody tr')].map((tr) => tr.querySelector('th').textContent), ['Noviembre de 2026', 'Octubre de 2026', 'Diciembre de 2025']);
  assert.match(months.textContent, /lo que ha facturado OpenAI/i);
  assert.match(months.textContent, /no se convierte a euros/);
  assert.match(document.querySelector('[aria-label="Costes"]').textContent, /2,30\s€/); // the euro costs are untouched
});

test('with OpenAI billed and Google estimated the block says which part is which', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS, 'GET /server/ai-costs': { ...AI, source: 'mixed' } });
  await server.render({ main: main() });
  await settle();
  const text = document.querySelector('[aria-label="Gasto en IA mes a mes"]').textContent;
  assert.match(text, /OpenAI es lo que ha facturado/);
  assert.match(text, /lo de Google es una estimación/);
});

test('without a key of OpenAI the block says its figures are an estimate, and with no spend it says so', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS, 'GET /server/ai-costs': { ...AI, source: 'estimated', month: 0, year: 0, total: 0, since: null, months: [] } });
  await server.render({ main: main() });
  await settle();
  const months = document.querySelector('[aria-label="Gasto en IA mes a mes"]');
  assert.match(months.textContent, /Todavía no hay gasto de IA/);
  assert.match(months.textContent, /es una estimación/i);
});

test('when the AI spend cannot be read only its block says so and the rest of the page stays', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS, 'GET /server/ai-costs': json({ detail: 'boom' }, 500) });
  await server.render({ main: main() });
  await settle();
  assert.match(document.getElementById('svAi').textContent, /No se ha podido consultar el gasto de IA/);
  assert.equal(document.querySelectorAll('.sv-line').length, 5);
});
