// Challenges page (#/challenges): time-boxed goals made from templates. GET /challenges has the definitions with their
// progress, derived from the sessions; only the definition is stored. A group challenge is for every active player (any
// of them may leave it) and only an admin launches it; the admin panel has the full list.
import { api, jsonRequest } from '../../lib/api.js';
import { hoursLabel, launchMonths, percent, periodLine, timeLeft } from '../../lib/challenges.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { modalHeader, openModal } from '../../ui/modal.js';
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
        ${user.is_admin ? html`<button class="pf-btn" type="button" data-delete>Borrar</button>` : ''}
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
    : html`<div class="pf-empty">Todavía no hay retos. ${user.is_admin ? 'Lanza el primero.' : 'Cuando un administrador lance uno, saldrá aquí.'}</div>`);
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

async function launch() {
  const { pickGame } = await import('../admin/dialogs.js');
  const months = launchMonths();
  const m = openModal(html`
    ${modalHeader('Lanzar un juego del mes')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Todos los jugadores activos participan, y cada uno puede salirse después. Cuentan las horas jugadas a ese juego dentro del mes.</p>
      <div class="adm-field-game"><span>Juego</span>
        <input type="hidden" id="chGame" />
        <strong id="chGameName">Sin elegir</strong>
        <button type="button" class="adm-btn sm" id="chPick">Elegir…</button>
      </div>
      <label>Mes<select class="adm-input" name="month">${months.map((o) => html`<option value="${o.value}">${o.label}</option>`)}</select></label>
      <label>Horas mínimas por jugador<input class="adm-input" type="number" name="each" min="0.5" step="0.5" value="5" /></label>
      <label>Horas mínimas entre todos<input class="adm-input" type="number" name="total" min="0.5" step="0.5" value="20" /></label>
      <label class="adm-check"><input type="checkbox" name="announce" checked /> Avisar al grupo (Telegram y notificaciones)</label>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">Lanzar reto</button>
      </div>
    </form>`);
  const form = m.el.querySelector('form');
  const error = form.querySelector('.adm-error');
  form.querySelector('#chPick').addEventListener('click', async () => {
    const game = await pickGame();
    if (game) {
      form.querySelector('#chGame').value = game.id;
      form.querySelector('#chGameName').textContent = game.name;
    }
  });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    error.textContent = '';
    const game = form.querySelector('#chGame').value;
    if (!game) {
      error.textContent = 'Elige un juego';
      return;
    }
    try {
      await api('/challenges', jsonRequest('POST', {
        kind: 'game_of_month',
        options: { game_id: game, month: form.month.value, min_hours_each: Number(form.each.value), min_hours_total: Number(form.total.value) },
        announce: form.announce.checked,
      }));
      m.close();
      toast('Reto lanzado');
      await load();
    } catch (err) {
      error.textContent = err.message;
    }
  });
}

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  mount(main, html`
    <div class="wl-head">
      <h1 class="pf-title">Retos</h1>
      ${user.is_admin ? html`<button class="pf-btn primary" type="button" id="chLaunch">Lanzar reto</button>` : ''}
    </div>
    <p class="pf-sub cal-intro">Objetivos con fecha de fin para todo el grupo. Cada uno puede apuntarse o salirse.</p>
    <div id="chLists"><div class="loading-spinner">Cargando los retos...</div></div>`);
  main.querySelector('#chLaunch')?.addEventListener('click', launch);
  main.querySelector('#chLists').addEventListener('click', (e) => {
    const id = e.target.closest('[data-challenge]')?.dataset.challenge;
    const part = e.target.closest('[data-part]');
    if (id && part) change(id, { path: `/participation?joined=${part.dataset.part === 'join'}`, options: { method: 'PUT' } });
    const del = e.target.closest('[data-delete]');
    if (id && del) {
      // the second press confirms
      if (del.dataset.sure) change(id, { path: '', options: { method: 'DELETE' } });
      else {
        del.dataset.sure = '1';
        del.textContent = '¿Seguro? Pulsa otra vez';
      }
    }
  });
  await load();
}
