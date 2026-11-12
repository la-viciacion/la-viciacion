// "Uso de la app": what the app's AI (chat, game guide) has been used for and what it has cost, from the record of its calls
// (GET /manage/ai-usage/calls). It is an estimate: the tokens are measured and priced when each call is made. Of the calls
// the group paid for the admin sees who made them; of what a player paid with their own key, only the totals.
import { api } from '../../lib/api.js';
import { ALL, featureLabel, perCall, sourceLabel, statusLabel, tokens, unpricedNote } from '../../lib/ai-calls.js';
import { money, monthChoices, monthLabel, share } from '../../lib/ai-usage.js';
import { html, mount } from '../../lib/html.js';
import { errorState, statTile } from './components.js';
import { cardTitle } from '../../ui/info-tip.js';

const cost = (value) => money(value, 'usd');
const bar = (value, max) => html`<div class="adm-progress"><div style="width:${share(value, max)}%"></div></div>`;

function table(headers, rows) {
  return html`
    <div class="adm-table-wrap"><table class="adm-table">
      <thead><tr>${headers.map((h) => html`<th>${h}</th>`)}</tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

// One breakdown: its name, calls, estimated cost and a bar of the share of the cost (or of the calls when nothing has a price)
function breakdown(id, title, items, label = (name) => name, hint = '') {
  const top = Math.max(0, ...items.map((i) => i.cost));
  const topCalls = Math.max(0, ...items.map((i) => i.calls));
  return html`
    <section class="adm-set-card adm-calls-${id}">
      ${hint ? cardTitle(title, hint) : html`<h3>${title}</h3>`}
      ${items.length
        ? table(['', 'Llamadas', 'Coste', ''], items.map((i) => html`
            <tr><td>${label(i.name)}</td><td>${i.calls}</td><td>${i.unpriced === i.calls && i.calls ? 'sin precio' : cost(i.cost)}</td>
            <td style="width:30%">${bar(top ? i.cost : i.calls, top || topCalls)}</td></tr>`))
        : html`<div class="adm-sub">Sin llamadas.</div>`}
    </section>`;
}

function players(items) {
  return html`
    <section class="adm-set-card adm-calls-players">
      ${cardTitle('Gasto de la clave del grupo, por jugador', html`Solo lo que ha pagado el grupo. Lo que cada jugador paga con su propia clave no se detalla por nombre.`)}
      ${items.length
        ? table(['Jugador', 'Llamadas', 'Coste', 'Tokens (entrada / salida)'], items.map((i) => html`
            <tr><td>${i.name}</td><td>${i.calls}</td><td>${cost(i.cost)}</td><td>${tokens(i.input_tokens)} / ${tokens(i.output_tokens)}</td></tr>`))
        : html`<div class="adm-sub">Todavía nadie ha usado la clave del grupo.</div>`}
    </section>`;
}

function detail(data, month) {
  const { total } = data;
  const note = unpricedNote(total);
  const average = perCall(total);
  return html`
    <div class="adm-stats">
      ${statTile(month === ALL ? 'Coste estimado' : monthLabel(month), cost(total.cost))}
      ${statTile('Llamadas', total.calls)}
      ${statTile('Coste medio por llamada', average == null ? '—' : cost(average))}
      ${statTile('Tokens (entrada / salida)', `${tokens(total.input_tokens)} / ${tokens(total.output_tokens)}`)}
      ${total.web_searches ? statTile('Búsquedas web', total.web_searches) : ''}
    </div>
    ${note ? html`<div class="adm-warn">${note} Si es un modelo nuevo, sus precios llegan con la siguiente actualización de la lista.</div>` : ''}
    ${breakdown('source', 'Quién ha pagado', data.by_source, sourceLabel)}
    ${month === ALL ? html`
      <section class="adm-set-card adm-calls-months">
        <h3>Por mes</h3>
        ${data.months.length
          ? table(['Mes', 'Llamadas', 'Clave del grupo', 'Claves propias', ''], data.months.slice().reverse().map((m) => html`
              <tr><td>${monthLabel(m.month)}</td><td>${m.calls}</td><td>${cost(m.group_cost)}</td><td>${cost(m.user_cost)}</td>
              <td style="width:25%">${bar(m.cost, Math.max(...data.months.map((x) => x.cost)))}</td></tr>`))
          : html`<div class="adm-sub">Sin llamadas.</div>`}
      </section>` : html`
      <section class="adm-set-card adm-calls-days">
        <h3>Por día</h3>
        ${data.days.length
          ? table(['Día', 'Llamadas', 'Coste', ''], data.days.map((d) => html`
              <tr><td>${d.date}</td><td>${d.calls}</td><td>${cost(d.cost)}</td><td style="width:30%">${bar(d.cost, Math.max(...data.days.map((x) => x.cost)))}</td></tr>`))
          : html`<div class="adm-sub">Sin llamadas.</div>`}
      </section>`}
    ${players(data.group_paid_by_user)}
    ${breakdown('feature', 'Por función', data.by_feature, featureLabel)}
    ${breakdown('model', 'Por modelo', data.by_model)}
    ${breakdown('tools', 'Por tipo de pregunta', data.by_tools, (name) => name, 'Las herramientas que ha llamado cada pregunta: dicen de qué iba sin guardar lo que se preguntó. Una pregunta sin herramientas responde de memoria; «web_search» es la guía buscando en internet. De los avisos que escribe la IA sola, aquí sale cuál es (por ejemplo «completed_game»).')}
    <section class="adm-set-card adm-calls-status">
      <h3>Cómo han acabado</h3>
      ${table(['Estado', 'Llamadas'], data.by_status.map((s) => html`<tr><td>${statusLabel(s.name)}</td><td>${s.calls}</td></tr>`))}
    </section>`;
}

function view(data, month) {
  const refresh = data.price_refresh_hours;
  const prices = refresh
    ? `Los precios se actualizan cada ${refresh} h${data.price_updates_running ? '' : ' (desde el próximo arranque de la API)'}.`
    : 'Los precios no se actualizan: se usan los de la versión instalada.';
  return html`
    <section class="adm-set-card adm-calls-head">
      ${cardTitle('Uso de la IA de la app', html`Cada pregunta al chat o a la guía deja una fila con sus tokens, lo que costó y de qué tipo era (nunca el texto). El coste es una <strong>estimación</strong>: los tokens medidos por el precio de su modelo el día de la llamada, más las búsquedas web a su precio${data.price_stamp ? ` (lista de precios de ${data.price_stamp.slice(0, 10)})` : ''}. ${prices} ${data.retention_days ? `Se conservan ${data.retention_days} días.` : 'Se conservan siempre.'} Los límites y el presupuesto se gestionan en IA → Límites.`)}
      <div class="adm-set-row">
        <label>Periodo
          <select class="adm-input" id="aicMonth">
            <option value="${ALL}" ${month === ALL ? 'selected' : ''}>Todo</option>
            ${monthChoices(data).map((m) => html`<option value="${m}" ${m === month ? 'selected' : ''}>${monthLabel(m)}</option>`)}
          </select>
        </label>
      </div>
    </section>
    <div id="aicDetail">${detail(data, month)}</div>`;
}

/** Draws the page's first half into `target`: the record of the app's calls. A failure here shows only here. */
export async function renderCalls(target) {
  let month = ALL;
  const load = () => api(`/manage/ai-usage/calls${month === ALL ? '' : `?month=${month}`}`);
  try {
    let data = await load();
    mount(target, view(data, month));
    target.onchange = async (e) => {
      if (e.target.id !== 'aicMonth') return;
      month = e.target.value;
      try {
        data = await load();
        mount(target.querySelector('#aicDetail'), detail(data, month));
      } catch (err) {
        mount(target.querySelector('#aicDetail'), errorState(err.message));
      }
    };
  } catch (err) {
    mount(target, errorState(err.message));
  }
}
