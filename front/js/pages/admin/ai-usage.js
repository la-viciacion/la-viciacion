// "Uso de IA": what OpenAI has billed in the last year (all it keeps), in total or for one month, with the line items and the days.
// It comes from OpenAI's Costs API (the API asks for it with OPENAI_ADMIN_KEY); Google has no such API, so it is not here.
import { api } from '../../lib/api.js';
import { ALL, money, monthChoices, monthLabel, selection, share } from '../../lib/ai-usage.js';
import { html, mount } from '../../lib/html.js';
import { statTile, errorState } from './components.js';

let panel;
let data;
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
  return html`
    <div class="adm-stats">
      ${statTile(month === ALL ? 'Gasto del último año' : monthLabel(month), cost(shown.total))}
      ${statTile('Meses con gasto', data.months.length)}
    </div>
    ${month === ALL ? html`
      <section class="adm-set-card">
        <h3>Por mes</h3>
        ${tableView(['Mes', 'Gasto', ''], data.months.slice().reverse().map((m) => html`
          <tr><td>${monthLabel(m.month)}</td><td>${cost(m.total)}</td><td style="width:35%">${bar(m.total, Math.max(...data.months.map((x) => x.total)))}</td></tr>`))}
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
    <div class="adm-settings">
      <section class="adm-set-card">
        <h3>Gasto en OpenAI</h3>
        <div class="adm-sub">Lo facturado por OpenAI en toda la organización (no solo por esta app), día a día en UTC. OpenAI solo conserva el último año de gasto. Los datos pueden tardar un rato en aparecer. No es el saldo que queda: OpenAI no lo ofrece por API, míralo en platform.openai.com → Billing.</div>
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
      <div id="aiuDetail">${detailView(selection(data, month))}</div>
    </div>`;
}

async function load(refresh) {
  const result = await api(`/manage/ai-usage${refresh ? '?refresh=true' : ''}`);
  if (!result.configured) {
    mount(panel, html`<section class="adm-set-card"><h3>Gasto en OpenAI</h3><div class="adm-warn">Falta <code>OPENAI_ADMIN_KEY</code> en el .env del servidor (una clave de administración de OpenAI, o una restringida con el permiso <code>api.usage.read</code>) y reiniciar la API. Mira Sistema → Servicios.</div></section>`);
    return;
  }
  data = result;
  if (month !== ALL && !data.months.some((m) => m.month === month)) month = ALL;
  mount(panel, view());
}

export async function render(target) {
  panel = target;
  month = ALL;
  try {
    await load(false);
    panel.onchange = (e) => {
      if (e.target.id !== 'aiuMonth') return;
      month = e.target.value;
      mount(panel.querySelector('#aiuDetail'), detailView(selection(data, month)));
    };
    panel.onclick = async (e) => {
      if (!e.target.closest('#aiuRefresh')) return;
      try {
        await load(true);
      } catch (err) {
        mount(panel, errorState(err.message));
      }
    };
  } catch (err) {
    mount(panel, errorState(err.message));
  }
}
