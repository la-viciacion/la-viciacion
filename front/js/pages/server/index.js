// Server page (#/server): how the machine the app runs on is doing, the month's traffic and what keeping the app running
// costs, by kind (server, domain...), for everybody. GET /server/status (Hetzner and Prometheus, the cost derived from the
// recorded rates: nothing is stored by this page).
import { api } from '../../lib/api.js';
import { formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { WINDOWS, bytes, load, money, monthYear, last, linePoints, peak, percent, rate, sharedMax, trafficShare, uptime } from '../../lib/server.js';

export const active = null; // it belongs to no item of the top bar

const WIDTH = 300;
const HEIGHT = 80;

const legend = (items) => html`<div class="sv-legend">${items.map(([cls, label, value]) => html`
  <span class="sv-key ${cls}"><span class="sv-dot"></span>${label} <strong>${value}</strong></span>`)}</div>`;

// One chart: every series drawn on the same scale, `max` at the top.
const chart = (title, label, series, max, from, to, items) => html`
  <section class="pf-card sv-card" aria-label="${title}">
    <h2 class="sv-title">${title}</h2>
    <svg class="sv-chart" viewBox="0 0 ${WIDTH} ${HEIGHT}" preserveAspectRatio="none" role="img" aria-label="${label}">
      <line class="sv-grid" x1="0" y1="${HEIGHT / 2}" x2="${WIDTH}" y2="${HEIGHT / 2}" />
      ${series.map(([cls, points]) => html`<polyline class="sv-line ${cls}" points="${linePoints(points, { width: WIDTH, height: HEIGHT, max, from, to })}" />`)}
    </svg>
    ${legend(items)}
  </section>`;

const header = (server) => html`
  <section class="pf-card sv-head">
    <div class="pf-sub">${server.type} · ${server.cores} vCPU · ${server.memory_gb} GB RAM · ${server.disk_gb} GB de disco · ${server.location}</div>
  </section>`;

const traffic = (t) => html`
  <section class="pf-card sv-card" aria-label="Tráfico del mes">
    <h2 class="sv-title">Tráfico de este mes</h2>
    <div class="sv-meter" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(trafficShare(t) * 100)}">
      <div class="sv-meter-fill${trafficShare(t) >= 0.9 ? ' high' : ''}" style="width: ${(trafficShare(t) * 100).toFixed(1)}%"></div>
    </div>
    <div class="pf-sub">Salida ${bytes(t.out)} de ${bytes(t.included)} incluidos · entrada ${bytes(t.in)}</div>
  </section>`;

// Memory and disk space as the percentage used over the period; the numbers are the ones of right now.
const usage = (title, label, part, range) => chart(title, label, [['cpu', part.series]], 100, range.from, range.to,
  [['cpu', 'Usado', percent(last(part.series))], ['muted', 'En uso', `${bytes(part.used)} de ${bytes(part.total)}`]]);

const machine = (host) => html`
  <section class="pf-card sv-card" aria-label="Carga de la máquina">
    <h2 class="sv-title">Carga y tiempo encendido</h2>
    ${host.load ? html`<div class="sv-cost">${host.load.map(load).join(' · ')} <span class="pf-sub">a 1, 5 y 15 min${host.cores ? ` (${host.cores} ${host.cores === 1 ? 'núcleo' : 'núcleos'})` : ''}</span></div>` : ''}
    ${host.uptime == null ? '' : html`<div class="pf-sub">Encendido desde hace ${uptime(host.uptime)}</div>`}
  </section>`;

const hostCards = (host, range) => {
  if (!host) return '';
  return html`
    ${host.memory ? usage('Memoria', 'Memoria usada', host.memory, range) : ''}
    ${host.disk ? usage('Espacio en disco', 'Espacio de disco usado', host.disk, range) : ''}
    ${machine(host)}`;
};

const COST_KINDS = { server: 'Servidor', domain: 'Dominio', other: 'Otros gastos' };

const tile = (label, cost, sub) => html`
  <div class="pf-card sv-tile"><div class="sv-tile-label">${label}</div><div class="sv-tile-value">${money(cost)}</div><div class="pf-sub">${sub}</div></div>`;

const kindRow = (label, kind) => html`
  <tr><th scope="row">${label}</th><td>${money(kind.month.so_far)}</td><td>${money(kind.year.so_far)}</td><td>${money(kind.total.so_far)}</td></tr>`;

// What keeping the app running costs: the three figures that matter, and where the money goes
const costs = (c) => html`
  <div class="sv-section"><h2 class="sv-section-title">Costes</h2></div>
  <div class="sv-tiles" aria-label="Costes">
    ${tile('Este mes', c.month.so_far, `previsto ${money(c.month.projected)}`)}
    ${tile('Este año', c.year.so_far, `previsto ${money(c.year.projected)}`)}
    ${tile('Desde el inicio', c.total.so_far, `desde ${monthYear(c.total.since)}`)}
  </div>
  <section class="pf-card sv-card" aria-label="Desglose de costes">
    <h2 class="sv-title">Desglose</h2>
    <table class="sv-table">
      <thead><tr><th scope="col">Concepto</th><th scope="col">Este mes</th><th scope="col">Este año</th><th scope="col">Desde el inicio</th></tr></thead>
      <tbody>${c.kinds.map((kind) => kindRow(COST_KINDS[kind.kind] ?? kind.kind, kind))}</tbody>
      ${c.kinds.length > 1 ? html`<tfoot>${kindRow('Total', c)}</tfoot>` : ''}
    </table>
    <div class="pf-sub">Es una estimación.</div>
  </section>`;

function panel(data, range) {
  const { server, metrics: m } = data;
  const to = Math.max(0, ...Object.values(m).map((points) => (points.length ? points[points.length - 1][0] : 0)));
  const from = to - WINDOWS.find(([key]) => key === range)[2];
  const net = sharedMax(m.net_in, m.net_out);
  const disk = sharedMax(m.disk_read, m.disk_write);
  return html`
    ${header(server)}
    <div class="sv-section">
      <h2 class="sv-section-title">Rendimiento</h2>
      <div class="pf-season" role="group" aria-label="Periodo de las gráficas">${WINDOWS.map(([key, label]) => html`
        <button type="button" class="pf-season-badge" data-window="${key}" aria-pressed="${String(key === range)}">${label}</button>`)}
      </div>
    </div>
    <div class="sv-grid-cards">
      ${chart('CPU', 'Uso de CPU', [['cpu', m.cpu]], 100, from, to, [['cpu', 'Ahora', percent(last(m.cpu))], ['muted', 'Máximo', percent(peak(m.cpu))]])}
      ${hostCards(data.host, { from, to })}
      ${chart('Red', 'Tráfico de red', [['in', m.net_in], ['out', m.net_out]], net, from, to,
        [['in', 'Entrada', rate(last(m.net_in))], ['out', 'Salida', rate(last(m.net_out))]])}
      ${chart('Disco', 'Lectura y escritura de disco', [['in', m.disk_read], ['out', m.disk_write]], disk, from, to,
        [['in', 'Lectura', rate(last(m.disk_read))], ['out', 'Escritura', rate(last(m.disk_write))]])}
    </div>
    <div class="sv-section"><h2 class="sv-section-title">Tráfico del mes</h2></div>
    ${traffic(server.traffic)}
    ${data.cost ? costs(data.cost) : ''}
    <div class="pf-sub sv-foot">Actualizado ${formatRelative(data.fetched_at)}.</div>`;
}

export async function render({ main }) {
  mount(main, html`
    <h1 class="pf-title pg-title">Servidor</h1>
    <div id="svBody"><div class="loading-spinner">Consultando el servidor...</div></div>`);
  const body = main.querySelector('#svBody');
  const draw = async (range) => {
    try {
      const data = await api(`/server/status?range=${range}`);
      if (!data) return;
      if (!data.configured) {
        mount(body, html`<div class="pf-empty">El panel del servidor no está configurado todavía.</div>`);
        return;
      }
      mount(body, panel(data, range));
    } catch (err) {
      mount(body, html`<div class="pf-empty">Error consultando el servidor: ${err.message}</div>`);
    }
  };
  body.addEventListener('click', (e) => {
    const pill = e.target.closest('[data-window]');
    if (pill && pill.getAttribute('aria-pressed') !== 'true') draw(pill.dataset.window);
  });
  await draw('24h');
}
