// "Uso de IA": what OpenAI has billed in the last year (all it keeps), in total or for one month, with the line items and the days.
// It comes from OpenAI's Costs API (the API asks for it with OPENAI_ADMIN_KEY); Google has no such API, so it is not here (its estimate is in the record of calls above).
import { api } from '../../lib/api.js';
import { ALL, money, monthChoices, monthLabel, reconcile, selection, share } from '../../lib/ai-usage.js';
import { html, mount } from '../../lib/html.js';
import { renderCalls } from './ai-calls.js';
import { render as renderSettings } from './settings.js';
import { statTile, errorState } from './components.js';
import { cardTitle } from '../../ui/info-tip.js';

let panel; // the whole page
let billed; // its second half: what OpenAI has billed
let data;
let compared = []; // OpenAI's bill against the app's own estimate, month by month (empty if the record could not be read)
let month = ALL;

const bar = (value, max) => html`<div class="adm-progress"><div style="width:${share(value, max)}%"></div></div>`;

function tableView(headers, rows) {
  return html`
    <div class="adm-table-wrap"><table class="adm-table">
      <thead><tr>${headers.map((h) => html`<th>${h}</th>`)}</tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

function detailView(shown) {
  const cost = (value) => money(value, data.currency);
  const top = shown.items[0]?.amount ?? 0;
  const topDay = Math.max(0, ...shown.days.map((d) => d.total));
  const thisMonth = compared.find((c) => c.month === month);
  return html`
    <div class="adm-stats">
      ${statTile(month === ALL ? 'Gasto del último año' : monthLabel(month), cost(shown.total))}
      ${statTile('Meses con gasto', data.months.length)}
      ${thisMonth ? statTile('Estimado por la app', cost(thisMonth.estimated)) : ''}
      ${thisMonth ? statTile('Sin explicar', cost(thisMonth.difference)) : ''}
    </div>
    ${month === ALL ? html`
      <section class="adm-set-card">
        ${cardTitle('Por mes', html`<strong>Facturado</strong> es lo que cobra OpenAI. <strong>Estimado</strong> es lo que la app calcula que ha gastado la clave del grupo en OpenAI (los tokens de cada llamada por el precio de su modelo). <strong>Sin explicar</strong> es la resta: si es grande y positiva, hay gasto que la app no ha visto (otro uso de la misma cuenta, o un precio que ha cambiado). El mes en curso suele no cuadrar del todo: OpenAI tarda un rato en facturar. Lo que cada jugador paga con su propia clave no está aquí: va a su cuenta.`)}
        ${tableView(['Mes', 'Facturado', 'Estimado', 'Sin explicar', ''], compared.length
          ? compared.map((c) => html`
              <tr><td>${monthLabel(c.month)}</td><td>${cost(c.billed)}</td><td>${cost(c.estimated)}</td><td>${cost(c.difference)}</td>
              <td style="width:25%">${bar(c.billed, Math.max(...compared.map((x) => x.billed)))}</td></tr>`)
          : data.months.slice().reverse().map((m) => html`
              <tr><td>${monthLabel(m.month)}</td><td>${cost(m.total)}</td><td>—</td><td>—</td><td style="width:25%">${bar(m.total, Math.max(...data.months.map((x) => x.total)))}</td></tr>`))}
      </section>` : ''}
    <section class="adm-set-card">
      <h3>Por concepto</h3>
      ${shown.items.length
        ? tableView(['Concepto', 'Gasto', ''], shown.items.map((item) => html`
            <tr><td>${item.name}</td><td>${cost(item.amount)}</td><td style="width:35%">${bar(item.amount, top)}</td></tr>`))
        : html`<div class="adm-sub">Sin gasto.</div>`}
    </section>
    ${month === ALL ? '' : html`
      <section class="adm-set-card">
        <h3>Por día</h3>
        ${shown.days.length
          ? tableView(['Día', 'Gasto', ''], shown.days.map((d) => html`
              <tr><td>${d.date}</td><td>${cost(d.total)}</td><td style="width:35%">${bar(d.total, topDay)}</td></tr>`))
          : html`<div class="adm-sub">Sin gasto.</div>`}
      </section>`}`;
}

function view() {
  return html`
    <div class="adm-stack">
      <section class="adm-set-card">
        ${cardTitle('Gasto en OpenAI', html`Lo facturado por OpenAI en toda la organización (no solo por esta app), día a día en UTC. OpenAI solo conserva el último año de gasto. Los datos pueden tardar un rato en aparecer. No es el saldo que queda: OpenAI no lo ofrece por API, míralo en platform.openai.com → Billing. Aquí solo está OpenAI: Google no ofrece su gasto por API, y lo suyo solo aparece como estimación en el registro de la app, arriba.`)}
        <div class="adm-set-row">
          <label>Periodo
            <select class="adm-input" id="aiuMonth">
              <option value="${ALL}" ${month === ALL ? 'selected' : ''}>Último año</option>
              ${monthChoices(data).map((m) => html`<option value="${m}" ${m === month ? 'selected' : ''}>${monthLabel(m)}</option>`)}
            </select>
          </label>
        </div>
        <div><button type="button" class="adm-btn" id="aiuRefresh">Actualizar</button></div>
      </section>
      <div id="aiuDetail" class="adm-stack">${detailView(selection(data, month))}</div>
    </div>`;
}

async function load(refresh) {
  const result = await api(`/manage/ai-usage${refresh ? '?refresh=true' : ''}`);
  if (!result.configured) {
    mount(billed, html`<section class="adm-set-card"><h3>Gasto en OpenAI</h3><div class="adm-warn">Falta <code>OPENAI_ADMIN_KEY</code> en el .env del servidor (una clave de administración de OpenAI, o una restringida con el permiso <code>api.usage.read</code>) y reiniciar la API. Mira Notificaciones → Canales.</div></section>`);
    return;
  }
  data = result;
  try {
    compared = reconcile(data.months, (await api('/manage/ai-usage/calls')).months);
  } catch {
    compared = []; // the record failing must not hide what OpenAI billed
  }
  if (month !== ALL && !data.months.some((m) => m.month === month)) month = ALL;
  mount(billed, view());
}

export async function render(target) {
  panel = target;
  month = ALL;
  mount(panel, html`<div id="aicApp" class="adm-stack"></div><div id="aiuBilled" class="adm-stack"></div><div id="aicSettings" class="adm-stack"></div>`);
  billed = panel.querySelector('#aiuBilled');
  renderCalls(panel.querySelector('#aicApp')); // the record of the app's calls neither waits for OpenAI nor needs its key
  // How the cost is worked out and how long the record is kept: the settings of what this page shows, below it, with their own Guardar
  renderSettings(panel.querySelector('#aicSettings'), { entity: { sections: ['aicost'] } });
  try {
    await load(false);
    billed.onchange = (e) => {
      if (e.target.id !== 'aiuMonth') return;
      month = e.target.value;
      mount(billed.querySelector('#aiuDetail'), detailView(selection(data, month)));
    };
    billed.onclick = async (e) => {
      if (!e.target.closest('#aiuRefresh')) return;
      try {
        await load(true);
      } catch (err) {
        mount(billed, errorState(err.message));
      }
    };
  } catch (err) {
    mount(billed, errorState(err.message));
  }
}
