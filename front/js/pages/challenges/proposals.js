// The challenges a player proposes for the whole group (menu → Retos → Proponer un reto) and what the admins answered.
// GET/POST/DELETE /challenges/proposals: only the proposal is stored; an admin approves it (it becomes a challenge of
// the group) or rejects it with a note.
import { api, jsonRequest } from '../../lib/api.js';
import { PROPOSAL_KINDS, launchMonths, proposalStatus } from '../../lib/challenges.js';
import { html, mount } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { gameSearch, gameSearchField } from './game-search.js';

const number = (value) => (value === '' || value == null ? undefined : Number(value));

// The period: the chosen dates when there are any (they replace the month), otherwise the whole month
const period = (el) => (el.startsOn.value || el.endsOn.value ? { starts_on: el.startsOn.value || undefined, ends_on: el.endsOn.value || undefined } : { month: el.month.value });

// What each kind sends: the options the proposal is made of
const OPTIONS = {
  game_of_month: (el, state) => ({
    game_id: state.game?.id, ...period(el), min_hours_each: number(el.gameEach.value), min_hours_total: number(el.gameTotal.value), versus: el.versus.checked,
  }),
  themed: (el) => ({
    theme: el.theme.value, ...period(el), mode: el.mode.value, versus: el.versus.checked,
    ...(el.mode.value === 'play'
      ? { min_hours_each: number(el.themedEach.value), min_hours_total: number(el.themedTotal.value) }
      : { min_games_total: number(el.themedGames.value) }),
  }),
};

/** The list of the proposals of the player, into `el`; nothing at all when they have none (or it cannot be loaded). */
export async function showProposals(el) {
  let list;
  try {
    list = await api('/challenges/proposals');
  } catch {
    return;
  }
  if (!list?.length) return mount(el, html``);
  mount(el, html`
    <div class="section-header"><h2 class="section-title">Tus propuestas</h2><div class="section-line"></div></div>
    <div class="ch-list">
      ${list.map((p) => html`
        <article class="pf-card ch-card" data-proposal="${p.id}">
          <div class="ch-head">
            <div class="ch-title">${p.title}<div class="pf-sub">${p.label}</div></div>
            <span class="${p.status === 'rejected' ? 'pf-tag muted' : 'pf-tag'}" data-status="${p.status}">${proposalStatus(p).label}</span>
          </div>
          ${proposalStatus(p).detail ? html`<div class="pf-sub">${proposalStatus(p).detail}</div>` : ''}
          ${p.status === 'pending' ? html`<div class="ch-actions"><button class="pf-btn" type="button" data-withdraw>Retirar</button></div>` : ''}
        </article>`)}
    </div>`);
  el.onclick = async (e) => {
    const button = e.target.closest('[data-withdraw]');
    if (!button) return;
    if (!button.dataset.sure) { // the second press confirms
      button.dataset.sure = '1';
      button.textContent = '¿Seguro? Pulsa otra vez';
      return;
    }
    try {
      await api(`/challenges/proposals/${button.closest('[data-proposal]').dataset.proposal}`, { method: 'DELETE' });
      await showProposals(el);
    } catch (err) {
      toast(err.message, 'err');
    }
  };
}

/** The form to propose a challenge to the group. `onDone` runs after it is sent. */
export async function openProposalForm(onDone) {
  let themes;
  try {
    themes = await api('/challenges/themes');
  } catch (err) {
    toast(err.message, 'err');
    return;
  }
  const months = launchMonths();
  const m = openModal(html`
    ${modalHeader('Proponer un reto al grupo')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Un administrador decide si se lanza. Puedes tener hasta 3 propuestas esperando respuesta.</p>
      <label>Tipo de reto<select class="adm-input" name="kind">
        ${PROPOSAL_KINDS.map(([value, label]) => html`<option value="${value}">${label}</option>`)}
      </select></label>
      <div data-kind="game_of_month">
        <p class="adm-sub">Un juego, un mes, unas horas mínimas por jugador y un total entre todos.</p>
        ${gameSearchField}
        <label>Horas mínimas por jugador<input class="adm-input" type="number" name="gameEach" min="0.5" step="0.5" value="5" /></label>
        <label>Horas mínimas entre todos<input class="adm-input" type="number" name="gameTotal" min="0.5" step="0.5" value="20" /></label>
      </div>
      <div data-kind="themed" hidden>
        <p class="adm-sub">Una temática (Terror, Metroidvania, Medieval...) y lo que tiene que hacer cada jugador: vale cualquier juego de esa temática.</p>
        <label>Temática<select class="adm-input" name="theme">
          ${themes.length ? themes.map((t) => html`<option value="${t.theme}">${t.theme} (${t.games})</option>`) : html`<option value="">No hay temáticas</option>`}
        </select></label>
        <label>Objetivo<select class="adm-input" name="mode">
          <option value="play">Jugar unas horas</option>
          <option value="complete">Completar al menos un juego</option>
        </select></label>
        <label data-for="play">Horas mínimas por jugador<input class="adm-input" type="number" name="themedEach" min="0.5" step="0.5" value="2" /></label>
        <label data-for="play">Horas entre todos (opcional)<input class="adm-input" type="number" name="themedTotal" min="0.5" step="0.5" /></label>
        <label data-for="complete" hidden>Juegos completados entre todos (opcional)<input class="adm-input" type="number" name="themedGames" min="1" step="1" /></label>
      </div>
      <label>Mes<select class="adm-input" name="month">
        ${months.map((month) => html`<option value="${month.value}">${month.label}</option>`)}
      </select></label>
      <p class="adm-sub">O, si no es un mes entero, elige los días (sustituyen al mes). Puede empezar más adelante.</p>
      <label>Desde<input class="adm-input" type="date" name="startsOn" /></label>
      <label>Hasta<input class="adm-input" type="date" name="endsOn" /></label>
      <label class="adm-check"><input type="checkbox" name="versus" /> Además es una competición: gana quien más avance</label>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">Enviar propuesta</button>
      </div>
    </form>`);
  const form = m.el.querySelector('form');
  const state = { game: null };
  gameSearch(form, state);

  const refresh = () => {
    const kind = form.elements.kind.value;
    form.querySelectorAll('[data-kind]').forEach((box) => { box.hidden = box.dataset.kind !== kind; });
    const play = form.elements.mode.value === 'play';
    form.querySelectorAll('[data-for]').forEach((box) => { box.hidden = box.dataset.for !== (play ? 'play' : 'complete'); });
  };
  form.addEventListener('change', refresh);
  refresh();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const kind = form.elements.kind.value;
    const options = OPTIONS[kind](form.elements, state);
    try {
      await api('/challenges/proposals', jsonRequest('POST', { kind, options }));
      m.close();
      toast('Propuesta enviada');
      await onDone();
    } catch (err) {
      form.querySelector('.adm-error').textContent = err.message;
    }
  });
}
