// "Tope mensual por jugador": what each player may spend of the group's key this month and what they have spent
// (GET /manage/ai-usage/budgets, PUT /manage/ai-usage/budgets/{user_id}). Only what the group's key pays counts: what a player
// pays with their own key is never here. The default cap is a setting (IA → Límites → Tope mensual por jugador); here an admin gives
// one player another amount.
import { api, jsonRequest } from '../../lib/api.js';
import { capLabel, isNearly, isSpent, parseCap, spentShare } from '../../lib/ai-budget.js';
import { money } from '../../lib/ai-usage.js';
import { html, mount } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { badge, errorState } from './components.js';
import { cardTitle } from '../../ui/info-tip.js';

const state = (spent, cap) => (cap === 0 ? badge('Sin IA del grupo', 'red') : isSpent(spent, cap) ? badge('Agotado', 'red') : isNearly(spent, cap) ? badge('Casi agotado', 'orange') : '');
const bar = (spent, cap) => html`<div class="adm-progress"><div style="width:${spentShare(spent, cap)}%"></div></div>`;

function playerRow(p) {
  return html`
    <tr data-user="${p.user_id}">
      <td>${p.name}${p.is_active ? '' : html` ${badge('Inactivo', 'gray')}`}</td>
      <td>${p.calls}</td>
      <td>${money(p.spent)} ${state(p.spent, p.cap)}</td>
      <td style="width:18%">${p.cap ? bar(p.spent, p.cap) : ''}</td>
      <td>
        <input class="adm-input" type="text" inputmode="numeric" name="cap" value="${p.override ?? ''}" placeholder="${capLabel(p.cap)}" aria-label="Tope mensual de ${p.name}" style="width:7.5em" />
      </td>
      <td><button type="button" class="adm-btn sm" data-save="${p.user_id}">Guardar</button></td>
    </tr>`;
}

// what the caps cannot see: calls of a model whose price the list does not have
const unpricedWarning = (data) => (data.unpriced?.calls && (data.default_user_cap != null || data.players.some((p) => p.cap != null))
  ? html`<div class="adm-warn">${data.unpriced.calls} ${data.unpriced.calls === 1 ? 'llamada' : 'llamadas'} de este mes de la clave del grupo (${data.unpriced.models.join(', ')}) no tienen precio conocido: no cuentan en ningún tope y no se pueden limitar. Se arregla con la siguiente actualización de la lista de precios o cambiando de modelo.</div>`
  : '');

function view(data) {
  return html`
    <section class="adm-set-card adm-budgets-card">
      ${unpricedWarning(data)}
      ${cardTitle('Tope por jugador', html`Por defecto: ${capLabel(data.default_user_cap)} al mes cada uno. Escribe otro número para un jugador (0 = sin IA de la clave del grupo) o déjalo vacío para volver al de por defecto. Se cuenta por mes natural y se renueva el día 1.`)}
      <div class="adm-sub">Tope mensual en dólares enteros (por ejemplo, 5). Déjalo vacío para usar el de por defecto (${capLabel(data.default_user_cap)}); escribe 0 para quitarle la IA de la clave del grupo (si tiene su propia clave, sigue usándola), o un tope alto (hasta 10000) para darle más que a los demás. El texto gris es el tope que se aplica ahora.</div>
      ${data.players.length
        ? html`<div class="adm-table-wrap"><table class="adm-table">
            <thead><tr><th>Jugador</th><th>Llamadas</th><th>Gastado este mes</th><th></th><th>Tope (US$ al mes)</th><th></th></tr></thead>
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
    // Enter in a cap saves that cap: it must not submit the page's form, where this table sits among the limits
    target.onkeydown = (e) => {
      if (e.key !== 'Enter' || !e.target.matches('[name="cap"]')) return;
      e.preventDefault();
      e.target.closest('tr').querySelector('[data-save]').click();
    };
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
