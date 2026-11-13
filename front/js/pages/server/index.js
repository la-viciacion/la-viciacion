// Server page (#/server): how the machine the app runs on is doing, the month's traffic and what keeping the app running
// costs, by kind (server, domain...), for everybody. GET /server/status (Hetzner and Prometheus, the cost derived from the
// recorded rates: nothing is stored by this page). The AI's spend, in dollars, is its own block: GET /server/ai-costs.
import { api } from '../../lib/api.js';
import { money as formatMoney } from '../../lib/ai-usage.js';
import { formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { KIND_ORDER, LIMITS, WINDOWS, axisTicks, axisTime, barLayout, barTop, bytes, load, money, monthName, monthShort, monthTotal, monthYear, yearTotals, last, linePoints, peak, percent, rate, sharedMax, trafficShare, uptime } from '../../lib/server.js';

export const active = null; // it belongs to no item of the top bar

const WIDTH = 300;
const HEIGHT = 80;

const legend = (items) => html`<div class="sv-legend">${items.map(([cls, label, value]) => html`
  <span class="sv-key ${cls}"><span class="sv-dot"></span>${label} <strong>${value}</strong></span>`)}</div>`;

// One chart: every series drawn on the same scale, `max` at the top, with its vertical axis (`format` writes the values), the time at
// both ends and, when `limit` is given, a dotted line at the most it should reach.
const chart = (title, label, series, max, from, to, items, { format, limit = null, range }) => html`
  <section class="pf-card sv-card" aria-label="${title}">
    <h2 class="sv-title">${title}</h2>
    <div class="sv-plot">
      <div class="sv-yaxis" aria-hidden="true">${axisTicks(max, format).map((tick) => html`<span>${tick}</span>`)}</div>
      <div class="sv-plot-area">
        <svg class="sv-chart" viewBox="0 0 ${WIDTH} ${HEIGHT}" preserveAspectRatio="none" role="img" aria-label="${label}">
          <line class="sv-grid" x1="0" y1="${HEIGHT / 2}" x2="${WIDTH}" y2="${HEIGHT / 2}" />
          ${limit !== null && limit <= max ? html`<line class="sv-limit" x1="0" y1="${(HEIGHT - (limit / max) * HEIGHT).toFixed(1)}" x2="${WIDTH}" y2="${(HEIGHT - (limit / max) * HEIGHT).toFixed(1)}" />` : ''}
          ${series.map(([cls, points]) => html`<polyline class="sv-line ${cls}" points="${linePoints(points, { width: WIDTH, height: HEIGHT, max, from, to })}" />`)}
        </svg>
        ${to > 0 ? html`<div class="sv-xaxis" aria-hidden="true"><span>${axisTime(from, range)}</span><span>ahora</span></div>` : ''}
      </div>
    </div>
    ${legend(limit === null ? items : [...items, ['limit', 'Máximo recomendado', format(limit)]])}
  </section>`;

// What the machine is: each characteristic with what it is
const spec = (label, value) => html`<div class="sv-spec"><dt>${label}</dt><dd>${value}</dd></div>`;

const header = (server) => html`
  <section class="pf-card sv-head" aria-label="Características del servidor">
    <dl class="sv-specs">
      ${spec('Plan', server.type)}
      ${spec('CPU', `${server.cores} vCPU`)}
      ${spec('Memoria', `${server.memory_gb} GB`)}
      ${spec('Disco', `${server.disk_gb} GB`)}
      ${spec('Ubicación', server.location)}
    </dl>
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
const usage = (title, label, part, span, limit) => chart(title, label, [['cpu', part.series]], 100, span.from, span.to,
  [['cpu', 'Usado', percent(last(part.series))], ['muted', 'En uso', `${bytes(part.used)} de ${bytes(part.total)}`]], { format: percent, limit, range: span.range });

const machine = (host) => html`
  <section class="pf-card sv-card" aria-label="Carga de la máquina">
    <h2 class="sv-title">Carga y tiempo encendido</h2>
    ${host.load ? html`<div class="sv-cost">${host.load.map(load).join(' · ')} <span class="pf-sub">a 1, 5 y 15 min${host.cores ? ` (${host.cores} ${host.cores === 1 ? 'núcleo' : 'núcleos'})` : ''}</span></div>` : ''}
    ${host.uptime == null ? '' : html`<div class="pf-sub">Encendido desde hace ${uptime(host.uptime)}</div>`}
  </section>`;

const hostCards = (host, range) => {
  if (!host) return '';
  return html`
    ${host.memory ? usage('Memoria', 'Memoria usada', host.memory, range, LIMITS.memory) : ''}
    ${host.disk ? usage('Espacio en disco', 'Espacio de disco usado', host.disk, range, LIMITS.disk) : ''}
    ${machine(host)}`;
};

const COST_KINDS = { server: 'Servidor', domain: 'Dominio', other: 'Otros gastos' };

// The AI is billed in dollars and is never converted to euros (the rate changes every day): it goes beside the euros, never added to them
const dollars = (amount) => formatMoney(amount, 'usd');
const hasAi = (ai) => Boolean(ai && !ai.error && ai.total > 0);

// A figure of the costs: the euros of keeping the app running and, beside them, what the AI cost in dollars when it cost something
const tile = (label, euros, sub, usd = null) => html`
  <div class="pf-card sv-tile"><div class="sv-tile-label">${label}</div><div class="sv-tile-value">${euros === null ? '' : money(euros)}${usd === null ? '' : html`<span class="sv-tile-usd">${euros === null ? '' : ' + '}${dollars(usd)}</span>`}</div><div class="pf-sub">${sub}</div></div>`;

const periodHead = (first) => html`<tr><th scope="col">${first}</th><th scope="col">Este mes</th><th scope="col">Este año</th><th scope="col">Desde el inicio</th></tr>`;

const kindRow = (label, kind) => html`
  <tr><th scope="row">${label}</th><td>${money(kind.month.so_far)}</td><td>${money(kind.year.so_far)}</td><td>${money(kind.total.so_far)}</td></tr>`;

const KIND_CLASS = { server: 'k-server', domain: 'k-domain', other: 'k-other' };

const monthLabel = (month) => `${monthName(month)} de ${month.slice(0, 4)}`;
const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);

const percentOf = (share) => `${(share * 100).toFixed(1)}%`;

// The vertical axis of a bar chart: the top of the scale, half of it and zero, lined up with the grid lines behind the bars
const yAxis = (max, format) => html`<div class="sv-yaxis sv-xy-axis" aria-hidden="true">${axisTicks(max, format).map((tick) => html`<span>${tick}</span>`)}</div>`;

// A year of costs month by month: what was spent by kind, and what is still forecast on top (the running month and the ones to come).
// Real buttons, one per month, spread over the whole width with a limit to how fat a bar gets.
const bars = (months, selected) => {
  const layout = barLayout(months);
  return html`
    <div class="sv-xy sv-euro-chart">
      ${yAxis(barTop(months), money)}
      <div class="sv-xy-area">
    <div class="sv-bars" role="group" aria-label="Costes mes a mes">
      ${layout.map((bar, i) => html`
        <button type="button" class="sv-bar ${bar.state}${bar.month === selected ? ' selected' : ''}" data-month="${bar.month}"
                aria-pressed="${String(bar.month === selected)}" aria-label="${monthLabel(bar.month)}: ${money(monthTotal(months[i]))}">
          <span class="sv-bar-stack">
            ${bar.segments.map((seg) => html`<span class="sv-seg ${KIND_CLASS[seg.kind] ?? 'k-other'}" style="height: ${percentOf(seg.share)}"></span>`)}
            ${bar.forecast ? html`<span class="sv-forecast" style="height: ${percentOf(bar.forecast)}"></span>` : ''}
          </span>
          <span class="sv-bar-label">${monthShort(bar.month)}</span>
        </button>`)}
    </div>
      </div>
    </div>`;
};

// What the AI cost each month, by month number: only what the AI's answer has
const aiByMonth = (ai) => new Map((hasAi(ai) ? ai.months : []).map((m) => [m.month, m.total]));

// The AI under the bars, one small bar per month in the same columns, on a scale of its own (dollars cannot be stacked on euros)
const aiBars = (months, selected, ai) => {
  const spent = aiByMonth(ai);
  const values = months.map((month) => spent.get(month.month) ?? 0);
  const top = Math.max(0, ...values);
  if (!top) return '';
  return html`
    <div class="sv-ai-chart" role="group" aria-label="Gasto en IA mes a mes, en dólares">
      <div class="sv-ai-title">Gasto en IA de cada mes, en dólares (escala distinta a la de los euros de arriba)</div>
      <div class="sv-xy">
        ${yAxis(top, dollars)}
        <div class="sv-xy-area">
          <div class="sv-ai-bars">
            ${months.map((month, i) => html`
              <div class="sv-ai-col${month.month === selected ? ' selected' : ''}" role="img" aria-label="${monthLabel(month.month)}: ${dollars(values[i])} en IA" title="${monthLabel(month.month)}: ${dollars(values[i])}">
                <span class="sv-ai-cell">${values[i] ? html`<span class="sv-ai-bar" style="height: ${percentOf(values[i] / top)}"></span>` : ''}</span>
                <span class="sv-bar-label">${monthShort(month.month)}</span>
              </div>`)}
          </div>
        </div>
      </div>
    </div>`;
};

const kindLegend = (kinds, withForecast) => html`
  <div class="sv-legend">
    ${kinds.map((kind) => html`<span class="sv-key ${KIND_CLASS[kind] ?? 'k-other'}"><span class="sv-dot"></span>${COST_KINDS[kind] ?? kind}</span>`)}
    ${withForecast ? html`<span class="sv-key forecast"><span class="sv-dot"></span>Previsto</span>` : ''}
  </div>`;

// What one month cost, by kind, with what is left to spend when it is not over
const monthDetail = (month, ai) => {
  const kinds = Object.keys(month.kinds).sort((a, b) => KIND_ORDER.indexOf(a) - KIND_ORDER.indexOf(b));
  const rows = kinds.filter((kind) => month.kinds[kind] > 0).map((kind) => html`<tr><th scope="row">${COST_KINDS[kind] ?? kind}</th><td>${money(month.kinds[kind])}</td></tr>`);
  const label = { closed: 'Total', running: 'Total previsto', future: 'Total previsto' }[month.state];
  return html`
    <h3 class="sv-detail-title">${capital(monthLabel(month.month))}</h3>
    ${rows.length || month.forecast ? html`
      <table class="sv-table sv-detail">
        <tbody>
          ${rows}
          ${month.forecast > 0 ? html`<tr class="sv-pending"><th scope="row">Lo que queda previsto</th><td>${money(month.forecast)}</td></tr>` : ''}
        </tbody>
        <tfoot><tr><th scope="row">${label}</th><td>${money(monthTotal(month))}</td></tr></tfoot>
      </table>` : html`<div class="pf-sub">Sin gastos este mes.</div>`}
    ${aiByMonth(ai).get(month.month) ? html`<div class="sv-ai-line">IA: <strong>${dollars(aiByMonth(ai).get(month.month))}</strong> <span class="pf-sub">en dólares, aparte de los euros</span></div>` : ''}`;
};

// The year chosen: its months as bars (the running year with the forecast to December), the year's total and the month looked at
const yearCard = (view) => {
  const months = view.years.get(view.year);
  if (!months) return html`<div class="pf-empty">${view.error || 'Cargando...'}</div>`;
  const totals = yearTotals(months);
  const current = months.find((month) => month.month === view.month) ?? months[months.length - 1];
  const open = months.some((month) => month.state !== 'closed');
  return html`
    <div class="sv-year-head">
      <h2 class="sv-title">Mes a mes</h2>
      <div class="pf-season" role="group" aria-label="Año de los costes">${view.available.map((year) => html`
        <button type="button" class="pf-season-badge" data-year="${year}" aria-pressed="${String(year === view.year)}">${year}</button>`)}
      </div>
    </div>
    ${view.error ? html`<div class="pf-msg err" role="alert">${view.error}</div>` : ''}
    <div class="sv-cost-total"><strong>${money(totals.so_far)}</strong> en ${view.year}${open ? html` · <strong>${money(totals.projected)}</strong> previstos a fin de año` : ''}</div>
    ${bars(months, current.month)}
    ${aiBars(months, current.month, view.ai)}
    ${kindLegend(view.kinds, open)}
    <div class="sv-detail-box" aria-live="polite">${monthDetail(current, view.ai)}</div>`;
};

const PROVIDERS = { openai: 'OpenAI', google: 'Google', anthropic: 'Anthropic' };
const WAY = { billed: 'facturado', estimated: 'estimado' };
const AI_SOURCE = {
  billed: 'Lo que ha facturado OpenAI a la organización (solo conserva el último año de gasto).',
  mixed: 'OpenAI es lo que ha facturado (solo conserva el último año); lo de Google es una estimación de la app, porque Google no ofrece el gasto por API y, con una clave del plan gratuito, lo real puede ser 0 US$.',
  estimated: 'Es una estimación de lo que ha gastado la clave del grupo: no hay clave de administración de OpenAI para consultar lo facturado, y con una clave de Google del plan gratuito lo real puede ser menos.',
};

const aiRow = (label, figures) => html`
  <tr><th scope="row">${label}</th><td>${dollars(figures.month)}</td><td>${dollars(figures.year)}</td><td>${dollars(figures.total)}</td></tr>`;

// Where the AI's money goes, by provider: in dollars, in a section of its own of the breakdown and never added to the euros. Only
// totals, never who spent them.
const aiBreakdown = (ai) => {
  if (!ai) return '';
  if (ai.error) return html`<div class="pf-sub">No se ha podido consultar el gasto de IA: ${ai.error}</div>`;
  if (!hasAi(ai)) return html``; // the AI is not in use yet: the breakdown is what it was, with no section about it
  return html`
    <div class="sv-ai-section" aria-label="Desglose del gasto en IA">
      <h3 class="sv-subtitle">IA · en dólares</h3>
      <table class="sv-table">
        <thead>${periodHead('Proveedor')}</thead>
        <tbody>${ai.providers.map((p) => aiRow(`${PROVIDERS[p.provider] ?? p.provider} (${WAY[p.source]})`, p))}</tbody>
        ${ai.providers.length > 1 ? html`<tfoot>${aiRow('Total', ai)}</tfoot>` : ''}
      </table>
      <div class="pf-sub">${AI_SOURCE[ai.source] ?? ''} No se suma a los euros ni se convierte: la cotización cambia cada día.</div>
    </div>`;
};

// What keeping the app running costs: the three figures that matter (the euros of the rates and, beside them, the AI in dollars),
// where the money goes, and the history
const costs = (view) => {
  const c = view.cost;
  const ai = hasAi(view.ai) ? view.ai : null;
  if (!c && !ai) return html``; // with no rates and no AI spend there is nothing to say of costs
  return html`
    <div class="sv-section"><h2 class="sv-section-title">Costes</h2></div>
    ${c || ai ? html`
      <div class="sv-tiles" aria-label="Costes">
        ${tile('Este mes', c ? c.month.so_far : null, c ? `previsto ${money(c.month.projected)}` : 'en IA', ai ? ai.month : null)}
        ${tile('Este año', c ? c.year.so_far : null, c ? `previsto ${money(c.year.projected)}` : 'en IA', ai ? ai.year : null)}
        ${tile('Desde el inicio', c ? c.total.so_far : null, c ? `desde ${monthYear(c.total.since)}` : `desde ${monthLabel(ai.since)}`, ai ? ai.total : null)}
      </div>` : ''}
    <section class="pf-card sv-card" aria-label="Desglose de costes">
      <h2 class="sv-title">Desglose</h2>
      ${c ? html`
        <table class="sv-table">
          <thead>${periodHead('Concepto')}</thead>
          <tbody>${c.kinds.map((kind) => kindRow(COST_KINDS[kind.kind] ?? kind.kind, kind))}</tbody>
          ${c.kinds.length > 1 ? html`<tfoot>${kindRow('Total', c)}</tfoot>` : ''}
        </table>
        <div class="pf-sub">Es una estimación.</div>` : ''}
      ${aiBreakdown(view.ai)}
    </section>
    ${c ? html`<section class="pf-card sv-card" id="svYear" aria-label="Costes mes a mes">${yearCard(view)}</section>` : ''}`;
};

function panel(data, range, view) {
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
      ${chart('CPU', 'Uso de CPU', [['cpu', m.cpu]], 100, from, to, [['cpu', 'Ahora', percent(last(m.cpu))], ['muted', 'Máximo', percent(peak(m.cpu))]], { format: percent, limit: LIMITS.cpu, range })}
      ${hostCards(data.host, { from, to, range })}
      ${chart('Red', 'Tráfico de red', [['in', m.net_in], ['out', m.net_out]], net, from, to,
        [['in', 'Entrada', rate(last(m.net_in))], ['out', 'Salida', rate(last(m.net_out))]], { format: rate, range })}
      ${chart('Disco', 'Lectura y escritura de disco', [['in', m.disk_read], ['out', m.disk_write]], disk, from, to,
        [['in', 'Lectura', rate(last(m.disk_read))], ['out', 'Escritura', rate(last(m.disk_write))]], { format: rate, range })}
    </div>
    <div class="sv-section"><h2 class="sv-section-title">Tráfico del mes</h2></div>
    ${traffic(server.traffic)}
    <div id="svCosts" class="sv-stack">${costs(view)}</div>
    <div class="pf-sub sv-foot">Actualizado ${formatRelative(data.fetched_at).toLowerCase()}.</div>`;
}

const emptyView = () => ({ year: null, month: null, years: new Map(), available: [], kinds: [], error: '', cost: null, ai: null });

// The month to look at when a year is opened: the running one, else the last
const defaultMonth = (months) => (months.find((month) => month.state === 'running') ?? months[months.length - 1]).month;

export async function render({ main }) {
  mount(main, html`
    <h1 class="pf-title pg-title">Servidor</h1>
    <div id="svBody"><div class="loading-spinner">Consultando el servidor...</div></div>`);
  const body = main.querySelector('#svBody');
  const view = emptyView();

  // The running year comes with the answer; another one is asked for when it is chosen and remembered
  const take = (cost) => {
    const running = Number(cost.months[0].month.slice(0, 4));
    view.available = cost.years;
    view.kinds = KIND_ORDER.filter((kind) => cost.kinds.some((item) => item.kind === kind));
    view.years.set(running, cost.months);
    if (view.year === null || !view.years.has(view.year)) view.year = running;
    view.month = view.month && view.years.get(view.year).some((m) => m.month === view.month) ? view.month : defaultMonth(view.years.get(view.year));
  };
  const redrawYear = () => mount(body.querySelector('#svYear'), yearCard(view));

  const draw = async (range) => {
    try {
      const data = await api(`/server/status?range=${range}`);
      if (!data) return;
      if (!data.configured) {
        mount(body, html`<div class="pf-empty">El panel del servidor no está configurado todavía.</div>`);
        return;
      }
      view.cost = data.cost ?? null;
      if (data.cost) take(data.cost);
      mount(body, panel(data, range, view));
    } catch (err) {
      mount(body, html`<div class="pf-empty">Error consultando el servidor: ${err.message}</div>`);
    }
  };

  const pickYear = async (year) => {
    view.error = '';
    if (!view.years.has(year)) {
      try {
        view.years.set(year, (await api(`/server/costs?year=${year}`)).months);
      } catch (err) {
        view.error = `Error consultando los costes de ${year}: ${err.message}`;
      }
    }
    if (view.years.has(year)) {
      view.year = year;
      view.month = defaultMonth(view.years.get(year));
    }
    redrawYear();
  };

  const pickMonth = (month) => {
    view.month = month;
    redrawYear();
  };

  body.addEventListener('click', (e) => {
    const pill = e.target.closest('[data-window]');
    if (pill && pill.getAttribute('aria-pressed') !== 'true') return draw(pill.dataset.window);
    const year = e.target.closest('[data-year]');
    if (year && Number(year.dataset.year) !== view.year) return pickYear(Number(year.dataset.year));
    const bar = e.target.closest('[data-month]');
    if (bar) pickMonth(bar.dataset.month);
  });
  // The AI's spend is asked once and apart: a failure of it shows only in its own part of the costs, and the window of the charts keeps it
  const loadAi = async () => {
    try {
      view.ai = (await api('/server/ai-costs')) ?? null;
    } catch (err) {
      view.ai = { error: err.message };
    }
    const slot = body.querySelector('#svCosts');
    if (slot) mount(slot, costs(view));
  };

  await draw('24h');
  await loadAi();
}
