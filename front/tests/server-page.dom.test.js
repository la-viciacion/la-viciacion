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
  currency: 'usd', source: 'mixed', month: 0.5, year: 1.75, total: 5.75, since: '2025-12',
  months: [{ month: '2025-12', total: 4 }, { month: '2026-09', total: 1.0 }, { month: '2026-10', total: 0.25 }],
  providers: [
    { provider: 'google', source: 'estimated', month: 0.1, year: 0.35, total: 0.75 },
    { provider: 'openai', source: 'billed', month: 0.4, year: 1.4, total: 5 },
  ],
};
const NO_AI = { currency: 'usd', source: 'estimated', month: 0, year: 0, total: 0, since: null, months: [], providers: [] };
const squash = (el) => el.textContent.replace(/\s+/g, ' ').trim();
const open = async (ai = AI) => {
  installApi({ 'GET /server/status?range=24h': STATUS, 'GET /server/ai-costs': ai });
  await server.render({ main: main() });
  await settle();
};

test('the cost cards show the euros and, beside them, what the AI cost in dollars: never added together', async () => {
  await open();
  const tiles = [...document.querySelectorAll('.sv-tile')].map(squash);
  assert.match(tiles[0], /^Este mes2,30 € \+ 0,50 US\$previsto 5,88 €$/);
  assert.match(tiles[1], /^Este año40,50 € \+ 1,75 US\$previsto 44,10 €$/);
  assert.match(tiles[2], /^Desde el inicio120,25 € \+ 5,75 US\$desde diciembre de 2023$/);
});

test('with no AI spend the cards are the euros alone', async () => {
  await open(NO_AI);
  assert.deepEqual([...document.querySelectorAll('.sv-tile')].map(squash), ['Este mes2,30 €previsto 5,88 €', 'Este año40,50 €previsto 44,10 €', 'Desde el inicio120,25 €desde diciembre de 2023']);
});

test('the breakdown has a section of its own for the AI, by provider and with its total, in dollars and apart from the euros', async () => {
  await open();
  const costs = document.querySelector('[aria-label="Desglose de costes"]');
  assert.match(squash(costs.querySelector('table')), /Total.*€/); // the euro table is as it was
  const ai = costs.querySelector('.sv-ai-section');
  assert.equal(ai.querySelector('h3').textContent, 'IA · en dólares');
  const rows = [...ai.querySelectorAll('tr')].map((tr) => [...tr.children].map((c) => squash(c)).join('|'));
  assert.deepEqual(rows, [
    'Proveedor|Este mes|Este año|Desde el inicio',
    'Google (estimado)|0,10 US$|0,35 US$|0,75 US$',
    'OpenAI (facturado)|0,40 US$|1,40 US$|5,00 US$',
    'Total|0,50 US$|1,75 US$|5,75 US$',
  ]);
  assert.doesNotMatch(ai.textContent, /€/);
  assert.match(ai.textContent, /OpenAI es lo que ha facturado.*lo demás es una estimación/);
  assert.match(ai.textContent, /No se suma a los euros ni se convierte/);
});

test('with a single provider the AI section has no total row, and says how it is known', async () => {
  await open({ ...AI, source: 'billed', providers: [AI.providers[1]] });
  const ai = document.querySelector('.sv-ai-section');
  assert.equal(ai.querySelector('tfoot'), null);
  assert.match(ai.textContent, /Lo que ha facturado OpenAI/);
});

test('with the admin keys of OpenAI and Anthropic both are named as what was billed, and the rest is the estimate', async () => {
  const anthropic = { provider: 'anthropic', source: 'billed', month: 0.2, year: 0.6, total: 1.5 };
  await open({ ...AI, source: 'mixed', providers: [anthropic, ...AI.providers] });
  const ai = document.querySelector('.sv-ai-section');
  assert.match(squash(ai), /Anthropic \(facturado\)/);
  assert.match(ai.textContent, /Anthropic y OpenAI son lo que han facturado \(solo conservan el último año de gasto\); lo demás es una estimación/);
  await open({ ...AI, source: 'billed', providers: [anthropic, AI.providers[1]] });
  assert.match(document.querySelector('.sv-ai-section').textContent, /Lo que han facturado Anthropic y OpenAI a sus organizaciones/);
});

test('with no admin key at all it says which providers could be asked and that the figure is an estimate', async () => {
  await open({ ...AI, source: 'estimated', providers: [{ ...AI.providers[1], source: 'estimated' }] });
  assert.match(document.querySelector('.sv-ai-section').textContent, /ningún proveedor tiene clave de administración.*OpenAI y Anthropic la admiten/);
});

test('with no AI spend yet the page is what it was: no section, no bars and no AI beside the euros', async () => {
  await open(NO_AI);
  assert.equal(document.querySelector('.sv-ai-section'), null);
  assert.equal(document.querySelector('.sv-ai-chart'), null);
  assert.equal(document.querySelector('.sv-tile-usd'), null);
  assert.doesNotMatch(document.getElementById('svCosts').textContent, /IA|US\$/);
});

test('under the euro bars the AI has a row of its own on its own scale, and the month pressed says what the AI cost', async () => {
  await open();
  const chart = document.querySelector('.sv-ai-chart');
  assert.match(chart.textContent, /en dólares \(escala distinta a la de los euros/);
  assert.equal(chart.querySelectorAll('.sv-xy-axis span').length, 3); // the scale: the top, half of it and zero
  assert.equal(document.querySelectorAll('.sv-euro-chart .sv-xy-axis span').length, 3);
  const cells = [...chart.querySelectorAll('.sv-ai-col')];
  assert.equal(cells.length, 12); // the same twelve columns as the bars
  assert.equal(cells[8].querySelector('.sv-ai-bar').style.height, '100%'); // September, the year's highest
  assert.equal(cells[9].querySelector('.sv-ai-bar').style.height, '25%');
  assert.equal(cells[0].querySelector('.sv-ai-bar'), null); // a month with no AI spend draws nothing
  document.querySelector('[data-month="2026-09"]').click();
  await settle();
  assert.match(squash(document.querySelector('.sv-detail-box')), /IA: 1,00 US\$ en dólares, aparte de los euros/);
  assert.ok(document.querySelector('.sv-ai-col.selected'));
});

test('a month with no AI spend has no AI line in its detail', async () => {
  await open();
  document.querySelector('[data-month="2026-03"]').click();
  await settle();
  assert.doesNotMatch(document.querySelector('.sv-detail-box').textContent, /IA:/);
});

test('the costs are spaced one block from the next', async () => {
  await open();
  assert.ok(document.getElementById('svCosts').classList.contains('sv-stack'));
  assert.equal(document.querySelectorAll('#svCosts > .sv-card').length, 2); // the breakdown and the months
});

test('when the AI spend cannot be read only its part of the breakdown says so and the rest stays', async () => {
  installApi({ 'GET /server/status?range=24h': STATUS, 'GET /server/ai-costs': json({ detail: 'boom' }, 500) });
  await server.render({ main: main() });
  await settle();
  assert.match(document.querySelector('[aria-label="Desglose de costes"]').textContent, /No se ha podido consultar el gasto de IA/);
  assert.equal(document.querySelectorAll('.sv-line').length, 5);
  assert.deepEqual([...document.querySelectorAll('.sv-tile')].map(squash)[0], 'Este mes2,30 €previsto 5,88 €');
});

test('without euro rates but with AI spend the costs are the AI alone', async () => {
  installApi({ 'GET /server/status?range=24h': { ...STATUS, cost: null }, 'GET /server/ai-costs': AI });
  await server.render({ main: main() });
  await settle();
  assert.deepEqual([...document.querySelectorAll('.sv-tile')].map(squash), ['Este mes0,50 US$en IA', 'Este año1,75 US$en IA', 'Desde el inicio5,75 US$desde diciembre de 2025']);
  assert.equal(document.getElementById('svYear'), null);
});
