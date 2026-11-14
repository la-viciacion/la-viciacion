// "Uso de IA": what a provider has billed in the last year, in total or for one month, with the line items and the days. One block for
// each provider that says it with an admin key: OpenAI (OPENAI_ADMIN_KEY) and Anthropic (ANTHROPIC_ADMIN_KEY, only where the group has a
// key of Anthropic). Google has no such API, so it is not here (its estimate is in the record of calls above).
import { api } from '../../lib/api.js';
import { ALL, money, monthChoices, monthLabel, reconcile, selection, share } from '../../lib/ai-usage.js';
import { html, mount } from '../../lib/html.js';
import { renderCalls } from './ai-calls.js';
import { render as renderSettings } from './settings.js';
import { statTile, errorState } from './components.js';
import { cardTitle } from '../../ui/info-tip.js';

// What differs between the providers: the key that lets the API ask them, who has it and what to tell about their bill
const BILLED = [
  {
    provider: 'openai', name: 'OpenAI', variable: 'OPENAI_ADMIN_KEY', always: true,
    missing: html`una clave de administración de OpenAI, o una restringida con el permiso <code>api.usage.read</code>`,
    about: 'Lo facturado por OpenAI en toda la organización (no solo por esta app), día a día en UTC. OpenAI solo conserva el último año de gasto. Los datos pueden tardar un rato en aparecer. No es el saldo que queda: OpenAI no lo ofrece por API, míralo en platform.openai.com → Billing.',
  },
  {
    provider: 'anthropic', name: 'Anthropic', variable: 'ANTHROPIC_ADMIN_KEY', always: false,
    missing: html`una clave de administración de Anthropic (<code>sk-ant-admin01-...</code>): solo una organización de la consola de Anthropic la tiene, una cuenta individual debe crear antes su organización`,
    about: 'Lo facturado por Anthropic en toda la organización (no solo por esta app), día a día en UTC; no incluye el nivel Priority Tier. Los datos pueden tardar unos minutos en aparecer. No es el saldo que queda: Anthropic no lo ofrece por API, míralo en la consola → Billing.',
  },
];

const bar = (value, max) => html`<div class="adm-progress"><div style="width:${share(value, max)}%"></div></div>`;

function tableView(headers, rows) {
  return html`
    <div class="adm-table-wrap"><table class="adm-table">
      <thead><tr>${headers.map((h) => html`<th>${h}</th>`)}</tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

/** The block of one provider: what it has billed, its own period selector and its own Actualizar. A failure shows only here. */
function billedBlock(target, { provider, name, variable, always, missing, about }) {
  let data;
  let compared = []; // the provider's bill against the app's own estimate, month by month (empty if the record could not be read)
  let month = ALL;
  const id = (what) => `${what}-${provider}`;

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
          ${cardTitle('Por mes', html`<strong>Facturado</strong> es lo que cobra ${name}. <strong>Estimado</strong> es lo que la app calcula que ha gastado la clave del grupo en ${name} (los tokens de cada llamada por el precio de su modelo). <strong>Sin explicar</strong> es la resta: si es grande y positiva, hay gasto que la app no ha visto (otro uso de la misma cuenta, o un precio que ha cambiado). El mes en curso suele no cuadrar del todo: ${name} tarda un rato en facturar. Lo que cada jugador paga con su propia clave no está aquí: va a su cuenta.`)}
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
          ${cardTitle(`Gasto en ${name}`, about)}
          <div class="adm-set-row">
            <label>Periodo
              <select class="adm-input" id="${id('aiuMonth')}">
                <option value="${ALL}" ${month === ALL ? 'selected' : ''}>Último año</option>
                ${monthChoices(data).map((m) => html`<option value="${m}" ${m === month ? 'selected' : ''}>${monthLabel(m)}</option>`)}
              </select>
            </label>
          </div>
          <div><button type="button" class="adm-btn" id="${id('aiuRefresh')}">Actualizar</button></div>
        </section>
        <div id="${id('aiuDetail')}" class="adm-stack">${detailView(selection(data, month))}</div>
      </div>`;
  }

  async function load(refresh) {
    const query = [provider === 'openai' ? '' : `provider=${provider}`, refresh ? 'refresh=true' : ''].filter(Boolean).join('&');
    const result = await api(`/manage/ai-usage${query ? `?${query}` : ''}`);
    if (!result.configured) {
      // OpenAI's block is always there; another provider's only where the group has its key, so nobody is told to set up what they do not use
      if (always || result.provider_key) mount(target, html`<section class="adm-set-card"><h3>Gasto en ${name}</h3><div class="adm-warn">Falta <code>${variable}</code> en el .env del servidor (${missing}) y reiniciar la API. Mira Notificaciones → Canales.</div></section>`);
      else mount(target, html``);
      return;
    }
    data = result;
    try {
      compared = reconcile(data.months, (await api('/manage/ai-usage/calls')).months, provider);
    } catch {
      compared = []; // the record failing must not hide what the provider billed
    }
    if (month !== ALL && !data.months.some((m) => m.month === month)) month = ALL;
    mount(target, view());
  }

  return async function start() {
    try {
      await load(false);
      target.onchange = (e) => {
        if (e.target.id !== id('aiuMonth')) return;
        month = e.target.value;
        mount(target.querySelector(`#${id('aiuDetail')}`), detailView(selection(data, month)));
      };
      target.onclick = async (e) => {
        if (!e.target.closest(`#${id('aiuRefresh')}`)) return;
        try {
          await load(true);
        } catch (err) {
          mount(target, errorState(err.message));
        }
      };
    } catch (err) {
      mount(target, errorState(err.message));
    }
  };
}

export async function render(panel) {
  mount(panel, html`<div id="aicApp" class="adm-stack"></div>${BILLED.map((b) => html`<div id="aiuBilled-${b.provider}" class="adm-stack"></div>`)}<div id="aicSettings" class="adm-stack"></div>`);
  renderCalls(panel.querySelector('#aicApp')); // the record of the app's calls neither waits for a provider nor needs its key
  // How the cost is worked out and how long the record is kept: the settings of what this page shows, below it, with their own Guardar
  renderSettings(panel.querySelector('#aicSettings'), { entity: { sections: ['aicost'] } });
  await Promise.all(BILLED.map((b) => billedBlock(panel.querySelector(`#aiuBilled-${b.provider}`), b)()));
}
