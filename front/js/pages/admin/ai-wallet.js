// "Monedero de la clave del grupo": what each player has put in for the group's AI key, what it has spent of it and what is left
// (GET /manage/ai-usage/wallet, POST .../wallet/entries, PUT .../wallet/start). The balance of the OpenAI account is typed here only to
// compare it with the total available; it is not stored in the app, only remembered by this browser.
import { api, jsonRequest } from '../../lib/api.js';
import { gap, isEmpty, parseAmount, realBalance } from '../../lib/ai-wallet.js';
import { money } from '../../lib/ai-usage.js';
import { html, mount } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { badge, errorState, statTile } from './components.js';
import { cardTitle } from '../../ui/info-tip.js';

const OPENAI_KEY = 'lv.ai.openaiBalance';
const remembered = () => { try { return localStorage.getItem(OPENAI_KEY) ?? ''; } catch { return ''; } };
const remember = (value) => { try { localStorage.setItem(OPENAI_KEY, value); } catch { /* the comparison just starts empty next time */ } };

const day = (iso) => new Date(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' });

const playerRow = (p) => html`
  <tr data-user="${p.user_id}">
    <td>${p.name}${p.is_active ? '' : html` ${badge('Inactivo', 'gray')}`}</td>
    <td>${money(p.contributed)}</td>
    <td>${money(p.spent)}</td>
    <td class="${isEmpty(p.balance) ? 'adm-neg' : ''}">${money(p.balance)} ${isEmpty(p.balance) ? badge(p.balance < 0 ? 'En negativo' : 'Sin saldo', 'red') : ''}</td>
  </tr>`;

const entryRow = (e) => html`
  <tr>
    <td>${day(e.created_at)}</td>
    <td>${e.name ?? 'Cuenta borrada'}</td>
    <td>${money(e.usd)}</td>
    <td>${e.note ?? ''}</td>
    <td>${e.by ?? ''}</td>
  </tr>`;

// The accounts the providers report by themselves (OpenRouter), each with its error if it failed
const balancesView = (balances) => (balances.length
  ? html`<div class="adm-sub" data-balances>${balances.map((b) => (b.error
    ? html`<div>Saldo en ${b.provider === 'openrouter' ? 'OpenRouter' : b.provider}: no se ha podido consultar (${b.error}).</div>`
    : html`<div>Saldo real en ${b.provider === 'openrouter' ? 'OpenRouter' : b.provider}: <strong>${money(b.remaining)}</strong> (comprado ${money(b.credits)}, gastado ${money(b.usage)}).</div>`))}
    <button type="button" class="adm-btn sm" data-refresh-balances>Actualizar</button></div>`
  : '');

function compare(total, typed, balances) {
  const { parts, sum } = realBalance(parseFloat(String(typed).replace(',', '.')), balances);
  if (sum === null) return html`<div class="adm-sub">Escribe lo que ves en tu cuenta de OpenAI para ver si cuadra.</div>`;
  const of = parts.map((p) => `${p.name} ${money(p.amount)}`).join(' + ');
  const diff = gap(sum, total.available);
  if (diff === 0) return html`<div class="adm-sub">Cuadra: las cuentas (${of}) y el monedero dicen lo mismo.</div>`;
  return html`<div class="adm-sub ${diff < 0 ? 'adm-warn' : ''}">${diff > 0
    ? `En las cuentas (${of}) hay ${money(diff)} más de lo que dice el monedero (saldo sin repartir o gasto estimado de más).`
    : `En las cuentas (${of}) hay ${money(-diff)} menos de lo que dice el monedero (gasto real mayor que el estimado, o saldo no anotado).`}</div>`;
}

function view(data, balances) {
  const { total } = data;
  return html`
    <section class="adm-set-card adm-wallet-card">
      ${cardTitle('Monedero de la clave del grupo', html`Lo que cada jugador aporta para pagar la clave del grupo y lo que le queda. Se apunta cada aportación (en dólares, como factura OpenAI; una devolución o corrección es una aportación negativa) y el saldo de cada jugador es lo aportado menos lo que ha gastado de la clave del grupo desde que empezó el monedero (a su coste real; lo que paga con su propia clave no cuenta). Está apagado hasta la primera aportación: antes solo mandan los presupuestos mensuales. Con el monedero en marcha, un jugador sin saldo (0 o en negativo, porque el coste se conoce al acabar la pregunta) no puede usar la clave del grupo hasta que se le anote otra aportación; si tiene su propia clave, sigue con ella según el modo de «Quién asume el coste». Los presupuestos mensuales siguen valiendo además. Las aportaciones no se editan ni se borran: un error se corrige con otra.`)}
      ${data.active ? '' : html`<div class="adm-sub">El monedero está apagado: aún no hay ninguna aportación. La primera lo enciende y el gasto cuenta desde ese momento (o desde la fecha que elijas abajo).</div>`}
      <div class="adm-stats">
        ${statTile('Aportado', money(total.contributed))}
        ${statTile('Gastado de la clave del grupo', money(total.spent))}
        ${statTile('Disponible', money(total.available))}
      </div>
      <div class="adm-set-row">
        <label>Saldo real en OpenAI (US$) <input class="adm-input" type="text" inputmode="decimal" data-field="openai" value="${remembered()}" placeholder="para comparar" /></label>
      </div>
      <div data-balances-box>${balancesView(balances)}</div>
      <div data-compare>${compare(total, remembered(), balances)}</div>

      ${cardTitle('Anotar una aportación', html`Elige quién ha puesto el dinero y cuánto (por ejemplo 2 o 2,50; con signo menos, una devolución o corrección).`)}
      <div class="adm-set-row">
        <label>Jugador <select class="adm-input" data-field="user">${data.players.map((p) => html`<option value="${p.user_id}">${p.name}</option>`)}</select></label>
        <label>Importe (US$) <input class="adm-input" type="text" inputmode="decimal" data-field="amount" placeholder="2,00" style="width:7.5em" /></label>
        <label>Nota <input class="adm-input" type="text" data-field="note" maxlength="200" placeholder="opcional" /></label>
        <button type="button" class="adm-btn sm" data-add>Anotar</button>
      </div>

      ${cardTitle('Desde cuándo cuenta el gasto', html`Por defecto, desde el momento de la primera aportación: el gasto anterior no se resta a nadie. Si eliges una fecha, cuenta lo que gastó la clave del grupo desde ese día (a las 00:00). Déjalo vacío para volver a «desde la primera aportación».`)}
      <div class="adm-set-row">
        <label>Fecha de inicio <input class="adm-input" type="date" data-field="start" value="${data.start_setting ?? ''}" /></label>
        <button type="button" class="adm-btn sm" data-save-start>Guardar</button>
      </div>
      <div class="adm-sub">${data.start ? `Ahora cuenta desde el ${day(data.start)}.` : 'Sin fecha: empezará con la primera aportación.'}</div>

      ${cardTitle('Saldo de cada jugador', html`Aportado menos gastado de la clave del grupo desde que empezó el monedero. En rojo, quien ya no puede usar la clave del grupo.`)}
      ${data.players.length
        ? html`<div class="adm-table-wrap"><table class="adm-table">
            <thead><tr><th>Jugador</th><th>Aportado</th><th>Gastado</th><th>Saldo</th></tr></thead>
            <tbody>${data.players.map(playerRow)}</tbody>
          </table></div>`
        : html`<div class="adm-sub">No hay jugadores.</div>`}

      ${cardTitle('Últimas aportaciones', html`Las 50 más recientes, con quién las anotó. Una devolución o corrección sale con signo menos.`)}
      ${data.entries.length
        ? html`<div class="adm-table-wrap"><table class="adm-table">
            <thead><tr><th>Fecha</th><th>Jugador</th><th>Importe</th><th>Nota</th><th>Anotada por</th></tr></thead>
            <tbody>${data.entries.map(entryRow)}</tbody>
          </table></div>`
        : html`<div class="adm-sub">Todavía no hay ninguna.</div>`}
    </section>`;
}

/** Draws the wallet into `target`. A failure here shows only here. */
export async function renderWallet(target) {
  const field = (name) => target.querySelector(`[data-field="${name}"]`);
  try {
    let data = await api('/manage/ai-usage/wallet');
    // What the providers say they hold: it must not stop the wallet from showing, so a failure here is only no balances
    const askBalances = async (refresh = false) => api(`/manage/ai-usage/balances${refresh ? '?refresh=true' : ''}`).then((found) => found.balances ?? []).catch(() => []);
    let balances = await askBalances();
    const draw = () => mount(target, view(data, balances));
    draw();
    // Enter in a box does what its button does: it must not submit the page's form, where this card sits among the limits
    target.onkeydown = (e) => {
      if (e.key !== 'Enter' || !e.target.matches('[data-field]')) return;
      e.preventDefault();
      if (e.target.dataset.field === 'start') target.querySelector('[data-save-start]').click();
      else if (e.target.dataset.field !== 'openai') target.querySelector('[data-add]').click();
    };
    target.oninput = (e) => {
      if (!e.target.matches('[data-field="openai"]')) return;
      remember(e.target.value);
      mount(target.querySelector('[data-compare]'), compare(data.total, e.target.value, balances));
    };
    target.onclick = async (e) => {
      if (e.target.closest('[data-refresh-balances]')) {
        balances = await askBalances(true);
        mount(target.querySelector('[data-balances-box]'), balancesView(balances));
        mount(target.querySelector('[data-compare]'), compare(data.total, field('openai').value, balances));
        return;
      }
      const add = e.target.closest('[data-add]');
      const start = e.target.closest('[data-save-start]');
      if (!add && !start) return;
      const button = add ?? start;
      button.disabled = true;
      try {
        if (add) {
          const usd = parseAmount(field('amount').value);
          if (Number.isNaN(usd)) throw new Error('El importe son dólares con hasta dos decimales (por ejemplo 2,50), distinto de 0 y de hasta 10000');
          data = await api('/manage/ai-usage/wallet/entries', jsonRequest('POST', { user_id: Number(field('user').value), usd, note: field('note').value.trim() || null }));
          draw();
          toast(usd > 0 ? 'Aportación anotada' : 'Devolución anotada');
        } else {
          data = await api('/manage/ai-usage/wallet/start', jsonRequest('PUT', { date: field('start').value || null }));
          draw();
          toast(data.start_setting ? 'Fecha de inicio guardada' : 'Cuenta desde la primera aportación');
        }
      } catch (err) {
        toast(err.message, 'err');
        button.disabled = false;
      }
    };
  } catch (err) {
    mount(target, errorState(err.message));
  }
}
