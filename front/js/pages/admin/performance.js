// "Rendimiento": how the API is doing, from the metrics it exposes to Prometheus (GET /manage/performance): requests, the time it takes to
// answer, errors, what is in flight and the process's memory over a window, and the slowest and busiest routes. Nothing is stored by this page.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { WINDOWS, axisTicks, axisTime, last, linePoints, peak } from '../../lib/server.js';
import { count, duration, errorRate, memory, perMinute, shortRoute } from '../../lib/performance.js';
import { statTile, errorState } from './components.js';
import { cardTitle } from '../../ui/info-tip.js';

const WIDTH = 300;
const HEIGHT = 80;

// One line chart on its own scale, with its vertical axis (`format` writes the values) and the time at both ends
const chart = (title, label, points, range, format) => {
  const max = Math.max(peak(points), 1e-9);
  const from = points.length ? points[0][0] : 0;
  const to = points.length ? points[points.length - 1][0] : 0;
  return html`
    <section class="adm-set-card sv-card" aria-label="${title}">
      <h3 class="sv-title">${title}</h3>
      <div class="sv-plot">
        <div class="sv-yaxis" aria-hidden="true">${axisTicks(max, format).map((tick) => html`<span>${tick}</span>`)}</div>
        <div class="sv-plot-area">
          <svg class="sv-chart" viewBox="0 0 ${WIDTH} ${HEIGHT}" preserveAspectRatio="none" role="img" aria-label="${label}">
            <line class="sv-grid" x1="0" y1="${HEIGHT / 2}" x2="${WIDTH}" y2="${HEIGHT / 2}" />
            <polyline class="sv-line cpu" points="${linePoints(points, { width: WIDTH, height: HEIGHT, max, from, to })}" />
          </svg>
          ${points.length > 1 ? html`<div class="sv-xaxis" aria-hidden="true"><span>${axisTime(from, range)}</span><span>ahora</span></div>` : html`<div class="pf-sub">Sin datos todavía</div>`}
        </div>
      </div>
      <div class="sv-legend"><span class="sv-key cpu"><span class="sv-dot"></span>Último <strong>${format(last(points))}</strong></span></div>
    </section>`;
};

const routeTable = (title, rows) => html`
  <section class="adm-set-card">
    ${cardTitle(title, html`Solo las rutas con al menos 3 peticiones en el periodo. El tiempo es el percentil 95: el 95 % de las peticiones tarda menos que eso, estimado a partir de los tramos del histograma.`)}
    <div class="adm-table-wrap"><table class="adm-table">
      <thead><tr><th>Ruta</th><th>Peticiones</th><th>p95</th><th>Errores 5xx</th></tr></thead>
      <tbody>${rows.length
        ? rows.map((r) => html`<tr><td><code>${r.method} ${shortRoute(r.route)}</code></td><td>${count(r.requests)}</td><td>${duration(r.p95)}</td><td>${r.errors ? count(r.errors) : '—'}</td></tr>`)
        : html`<tr><td colspan="4">Aún no hay rutas con peticiones suficientes.</td></tr>`}</tbody>
    </table></div>
  </section>`;

function view(data, range) {
  const { now, charts, routes } = data;
  return html`
    <div class="adm-stack">
      <div class="pf-season" role="group" aria-label="Periodo">${WINDOWS.map(([key, label]) => html`
        <button type="button" class="pf-season-badge" data-window="${key}" aria-pressed="${String(key === range)}">${label}</button>`)}
        <button type="button" class="adm-btn" id="perfRefresh">Actualizar</button>
      </div>
      ${data.has_data ? '' : html`<div class="pf-sub">Prometheus aún no tiene peticiones de la API en este periodo: los datos empiezan a guardarse cuando se despliega esta versión y Prometheus la consulta (cada 30 s).</div>`}
      <div class="adm-stats">
        ${statTile('Peticiones', count(now.requests))}
        ${statTile('Tiempo p50', duration(now.p50))}
        ${statTile('Tiempo p95', duration(now.p95))}
        ${statTile('Errores 5xx', `${count(now.errors)} (${errorRate(now.requests, now.errors)})`)}
        ${statTile('En curso ahora', count(now.in_flight))}
        ${statTile('Memoria de la API', memory(now.memory))}
      </div>
      <div class="sv-grid-cards">
        ${chart('Peticiones por minuto', 'Peticiones por minuto', charts.requests, range, perMinute)}
        ${chart('Tiempo de respuesta p95', 'Tiempo de respuesta del percentil 95', charts.p95, range, duration)}
        ${chart('Errores 5xx por minuto', 'Errores 5xx por minuto', charts.errors, range, perMinute)}
        ${chart('Memoria de la API', 'Memoria usada por el proceso de la API', charts.memory, range, memory)}
      </div>
      ${routeTable('Rutas más lentas', routes.slowest)}
      ${routeTable('Rutas más pedidas', routes.busiest)}
    </div>`;
}

export async function render(panel) {
  // The panel is shared by every tab: the page lives in a container of its own, so its clicks go away with it and an answer that
  // arrives after the admin moved to another tab (the container is no longer in the document) is dropped instead of painted over it.
  mount(panel, html`<div id="perfRoot"></div>`);
  const root = panel.querySelector('#perfRoot');
  let range = '24h';

  async function draw(refresh = false) {
    try {
      const data = await api(`/manage/performance?range=${range}${refresh ? '&refresh=true' : ''}`);
      if (!data || !root.isConnected) return;
      if (!data.configured) {
        mount(root, errorState('La monitorización no está encendida: esta página necesita Prometheus (COMPOSE_PROFILES=monitoring en el .env).'));
        return;
      }
      mount(root, view(data, range));
    } catch (err) {
      if (root.isConnected) mount(root, errorState(err.message));
    }
  }

  root.onclick = (e) => {
    const pill = e.target.closest('[data-window]');
    if (pill && pill.getAttribute('aria-pressed') !== 'true') {
      range = pill.dataset.window;
      return draw();
    }
    if (e.target.closest('#perfRefresh')) return draw(true);
  };
  await draw();
}
