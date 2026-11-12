// "Presupuesto de la clave del grupo": how much of the month's budget the group's key has spent and what each player may spend of
// it (GET /manage/ai-usage/budgets, PUT /manage/ai-usage/budgets/{user_id}). Only what the group's key pays counts: what a player
// pays with their own key is never here. The default caps are settings (IA → Avisos con IA → Coste de la IA); here an admin gives one
// player another amount.
import { api, jsonRequest } from '../../lib/api.js';
import { budgetLine, capLabel, isNearly, isSpent, parseCap, spentShare } from '../../lib/ai-budget.js';
import { money } from '../../lib/ai-usage.js';
import { html, mount } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { badge, errorState, statTile } from './components.js';

const state = (spent, cap) => (isSpent(spent, cap) ? badge('Agotado', 'red') : isNearly(spent, cap) ? badge('Casi agotado', 'orange') : '');
const bar = (spent, cap) => html`<div class="adm-progress"><div style="width:${spentShare(spent, cap)}%"></div></div>`;

function playerRow(p) {
  return html`
    <tr data-user="${p.user_id}">
      <td>${p.name}${p.is_active ? '' : html` ${badge('Inactivo', 'gray')}`}</td>
      <td>${p.calls}</td>
      <td>${money(p.spent)} ${state(p.spent, p.cap)}</td>
      <td style="width:18%">${p.cap ? bar(p.spent, p.cap) : ''}</td>
      <td>
        <input class="adm-input" type="text" inputmode="numeric" name="cap" value="${p.override ?? ''}" placeholder="${capLabel(p.default ?? p.cap)}" aria-label="Tope mensual de ${p.name}" style="width:7.5em" />
      </td>
      <td><button type="button" class="adm-btn sm" data-save="${p.user_id}">Guardar</button></td>
    </tr>`;
}

// what the caps cannot see: calls of a model whose price the list does not have
const unpricedWarning = (data) => (data.unpriced?.calls && (data.group.cap || data.default_user_cap || data.players.some((p) => p.cap))
  ? html`<div class="adm-warn">${data.unpriced.calls} ${data.unpriced.calls === 1 ? 'llamada' : 'llamadas'} de este mes de la clave del grupo (${data.unpriced.models.join(', ')}) no tienen precio conocido: no cuentan en ningún presupuesto y no se pueden limitar. Se arregla con la siguiente actualización de la lista de precios o cambiando de modelo.</div>`
  : '');

function view(data) {
  const group = data.group;
  return html`
    <section class="adm-set-card adm-budgets-card">
      <h3>Presupuesto de la clave del grupo</h3>
      <div class="adm-sub">Lo que el grupo puede gastar al mes en preguntas que paga su clave (la del .env). Solo cuenta eso: lo que cada jugador paga con su propia clave no suma ni se limita. Los topes son en dólares enteros, y 0 es sin límite; el coste es una estimación y una pregunta puede pasarse del tope porque su precio se conoce al acabar. Se renuevan el día 1. Los topes por defecto se cambian en <strong>IA → Avisos con IA → Coste de la IA</strong>.</div>
      ${unpricedWarning(data)}
      <div class="adm-stats">${statTile(group.cap ? `Gastado este mes de ${money(group.cap)}` : 'Gastado este mes', money(group.spent))}</div>
      ${group.cap ? html`${bar(group.spent, group.cap)}<div class="adm-sub">${budgetLine('Grupo', group, data.resets_on)} ${state(group.spent, group.cap)}</div>` : html`<div class="adm-sub">El grupo no tiene tope: la clave del grupo no se limita por coste.</div>`}
      <h3>Tope por jugador</h3>
      <div class="adm-sub">Por defecto: ${capLabel(data.default_user_cap)} al mes cada uno. Escribe otro número para un jugador (0 = sin límite) o déjalo vacío para volver al de por defecto.</div>
      ${data.players.length
        ? html`<div class="adm-table-wrap"><table class="adm-table">
            <thead><tr><th>Jugador</th><th>Llamadas</th><th>Gastado este mes</th><th></th><th>Tope</th><th></th></tr></thead>
            <tbody>${data.players.map((p) => playerRow({ ...p, default: data.default_user_cap }))}</tbody>
          </table></div>`
        : html`<div class="adm-sub">No hay jugadores.</div>`}
    </section>`;
}

/** Draws the budgets into `target`. A failure here shows only here. */
export async function renderBudgets(target) {
  try {
    let data = await api('/manage/ai-usage/budgets');
    mount(target, view(data));
    target.onclick = async (e) => {
      const button = e.target.closest('[data-save]');
      if (!button) return;
      const row = button.closest('tr');
      const cap = parseCap(row.querySelector('[name="cap"]').value);
      if (Number.isNaN(cap)) return toast('El tope son dólares enteros, de 0 a 10000', 'err');
      button.disabled = true;
      try {
        await api(`/manage/ai-usage/budgets/${encodeURIComponent(button.dataset.save)}`, jsonRequest('PUT', { usd: cap }));
        data = await api('/manage/ai-usage/budgets');
        mount(target, view(data));
        toast(cap === null ? 'Vuelve el tope por defecto' : `Tope guardado: ${capLabel(cap)}`);
      } catch (err) {
        toast(err.message, 'err');
        button.disabled = false;
      }
    };
  } catch (err) {
    mount(target, errorState(err.message));
  }
}
