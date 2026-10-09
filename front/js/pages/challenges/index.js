// Challenges page (#/challenges): time-boxed goals made from templates. GET /challenges has the definitions with their
// progress, derived from the sessions; only the definition is stored. A group challenge is the app's: every active
// player takes part (any may leave it) and an admin launches and deletes it from the admin panel (Gestión de datos →
// Retos). From this page a player launches only their own, personal challenges.
import { api } from '../../lib/api.js';
import { hoursLabel, percent, periodLine, timeLeft } from '../../lib/challenges.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { toast } from '../../ui/toast.js';

export const active = null; // it belongs to no item of the top bar

let main;
let user;

const bar = (seconds, target) => html`<div class="ch-bar${seconds >= target ? ' ok' : ''}"><i style="width:${percent(seconds, target)}%"></i></div>`;

const playerRow = (p, me) => html`
  <div class="ch-row">
    <span class="ch-name">${p.name}${p.user_id === me ? ' (tú)' : ''}</span>
    ${bar(p.seconds, p.target_seconds)}
    <span class="pf-sub">${hoursLabel(p.seconds)} / ${hoursLabel(p.target_seconds)}</span>
  </div>`;

function card(c) {
  const tag = c.status === 'active' ? 'pf-tag' : 'pf-tag muted';
  const total = c.progress.total_target_seconds;
  return html`
    <article class="pf-card ch-card" data-challenge="${c.id}">
      <div class="ch-head">
        <div class="ch-title">
          ${c.game ? html`<a class="game-link" href="${gameHref(c.game.id)}">${c.title}</a>` : c.title}
          <div class="pf-sub">${periodLine(c)}</div>
        </div>
        <span class="${tag}">${timeLeft(c)}</span>
      </div>
      <div class="pf-sub">${c.label} · mínimo ${hoursLabel(c.params.min_hours_each * 3600)} cada uno y ${hoursLabel(c.params.min_hours_total * 3600)} entre todos</div>
      ${c.taking_part
        ? html`
          <div class="ch-players">${c.progress.players.map((p) => playerRow(p, user.id))}</div>
          <div class="ch-row ch-total">
            <span class="ch-name">Total</span>
            ${bar(c.progress.total_seconds, total)}
            <span class="pf-sub">${hoursLabel(c.progress.total_seconds)} / ${hoursLabel(total)}${c.progress.total_done ? ' ✓' : ''}</span>
          </div>`
        : html`<div class="pf-empty">No participas en este reto.</div>`}
      <div class="ch-actions">
        ${c.can_opt_out
          ? html`<button class="pf-btn" type="button" data-part="${c.taking_part ? 'leave' : 'join'}">${c.taking_part ? 'Dejar de participar' : 'Volver a participar'}</button>`
          : ''}
      </div>
    </article>`;
}

const section = (title, list, empty) => html`
  <div class="section-header"><h2 class="section-title">${title}</h2><div class="section-line"></div></div>
  ${list.length ? html`<div class="ch-list">${list.map(card)}</div>` : html`<div class="pf-empty">${empty}</div>`}`;

function draw(challenges) {
  const by = (status) => challenges.filter((c) => c.status === status);
  mount(main.querySelector('#chLists'), challenges.length
    ? html`
      ${section('En marcha', by('active'), 'No hay ningún reto en marcha.')}
      ${by('upcoming').length ? section('Próximos', by('upcoming'), '') : ''}
      ${by('finished').length ? section('Terminados', by('finished').slice(0, 10), '') : ''}`
    : html`<div class="pf-empty">Todavía no hay retos. Cuando haya uno, saldrá aquí.</div>`);
}

async function load() {
  try {
    const challenges = await api('/challenges');
    if (challenges) draw(challenges);
  } catch (err) {
    mount(main.querySelector('#chLists'), html`<div class="pf-empty">Error cargando los retos: ${err.message}</div>`);
  }
}

async function change(id, request) {
  try {
    await api(`/challenges/${id}${request.path}`, request.options);
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  mount(main, html`
    <h1 class="pf-title pg-title">Retos</h1>
    <p class="pf-sub cal-intro">Objetivos con fecha de fin. Los del grupo los lanza un administrador y cada uno puede salirse; los tuyos los lanzas tú y los ven los demás.</p>
    <div id="chLists"><div class="loading-spinner">Cargando los retos...</div></div>`);
  main.querySelector('#chLists').addEventListener('click', (e) => {
    const id = e.target.closest('[data-challenge]')?.dataset.challenge;
    const part = e.target.closest('[data-part]');
    if (id && part) change(id, { path: `/participation?joined=${part.dataset.part === 'join'}`, options: { method: 'PUT' } });
  });
  await load();
}
