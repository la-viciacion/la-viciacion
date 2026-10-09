// Challenges page (#/challenges): time-boxed goals made from templates. GET /challenges has the definitions with their
// progress, derived from the sessions; only the definition is stored. A group challenge is the app's: every active
// player takes part (any may leave it) and an admin launches and deletes it from the admin panel (Gestión de datos →
// Retos). From this page a player launches and deletes only their own, personal challenges.
import { api, jsonRequest } from '../../lib/api.js';
import { DURATIONS, amountLabel, blocks, partTarget, partValue, percent, periodLine, summaryLine, timeLeft } from '../../lib/challenges.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';

export const active = null; // it belongs to no item of the top bar

let main;
let user;

const bar = (part) => html`<div class="ch-bar${part.done ? ' ok' : ''}"><i style="width:${percent(partValue(part), partTarget(part))}%"></i></div>`;

const partRow = (p, me) => html`
  <div class="ch-row">
    <span class="ch-name">${p.name}${p.user_id === me ? ' (tú)' : ''}</span>
    ${bar(p)}
    <span class="pf-sub">${amountLabel(p)}${p.done ? ' ✓' : ''}</span>
  </div>`;

const totalRow = (c) => html`
  <div class="ch-row ch-total">
    <span class="ch-name">Total</span>
    <div class="ch-bar${c.progress.total_done ? ' ok' : ''}"><i style="width:${percent(c.progress.total_seconds, c.progress.total_target_seconds)}%"></i></div>
    <span class="pf-sub">${amountLabel({ seconds: c.progress.total_seconds, target_seconds: c.progress.total_target_seconds })}${c.progress.total_done ? ' ✓' : ''}</span>
  </div>`;

function card(c) {
  const mine = c.scope === 'user' && c.owner?.id === user.id;
  const hasTotal = c.progress.total_target_seconds !== undefined;
  const parts = html`<div class="ch-players">${c.progress.players.map((p) => partRow(p, user.id))}</div>${hasTotal ? totalRow(c) : ''}`;
  return html`
    <article class="pf-card ch-card" data-challenge="${c.id}">
      <div class="ch-head">
        <div class="ch-title">
          ${c.game ? html`<a class="game-link" href="${gameHref(c.game.id)}">${c.title}</a>` : c.title}
          <div class="pf-sub">${c.scope === 'user' && !mine ? `${c.owner?.name ?? 'Alguien'} · ` : ''}${periodLine(c)}</div>
        </div>
        <span class="${c.status === 'active' ? 'pf-tag' : 'pf-tag muted'}">${timeLeft(c)}</span>
      </div>
      <div class="pf-sub">${summaryLine(c)}</div>
      ${c.taking_part || c.scope === 'user' ? parts : html`<div class="pf-empty">No participas en este reto.</div>`}
      <div class="ch-actions">
        ${c.can_opt_out
          ? html`<button class="pf-btn" type="button" data-part="${c.taking_part ? 'leave' : 'join'}">${c.taking_part ? 'Dejar de participar' : 'Volver a participar'}</button>`
          : ''}
        ${mine ? html`<button class="pf-btn" type="button" data-delete>Borrar</button>` : ''}
      </div>
    </article>`;
}

const section = ({ title, list, empty }) => html`
  <div class="section-header"><h2 class="section-title">${title}</h2><div class="section-line"></div></div>
  ${list.length ? html`<div class="ch-list">${list.map(card)}</div>` : html`<div class="pf-empty">${empty}</div>`}`;

function draw(challenges) {
  mount(main.querySelector('#chLists'), html`${blocks(challenges, user.id).map(section)}`);
}

async function load() {
  try {
    const challenges = await api('/challenges');
    if (challenges) draw(challenges);
  } catch (err) {
    mount(main.querySelector('#chLists'), html`<div class="pf-empty">Error cargando los retos: ${err.message}</div>`);
  }
}

async function change(id, path, options) {
  try {
    await api(`/challenges/${id}${path}`, options);
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

/** The form of a personal "try a genre" challenge. */
async function launchGenre() {
  let genres;
  try {
    genres = await api('/challenges/genres');
  } catch (err) {
    toast(err.message, 'err');
    return;
  }
  if (!genres?.length) {
    toast('Todavía no hay géneros en la base de datos', 'err');
    return;
  }
  const m = openModal(html`
    ${modalHeader('Probar un género')}
    <form class="adm-form" novalidate>
      <p class="adm-sub">Elige un género y cuánto quieres jugarlo. Solo cuentan los juegos de ese género que no tuvieras antes de empezar el reto, desde hoy.</p>
      <label>Género<select class="adm-input" name="genre">
        ${genres.map((g) => html`<option value="${g.genre}">${g.genre} (${g.games})${g.played ? '' : ' · nuevo para ti'}</option>`)}
      </select></label>
      <label>Objetivo<select class="adm-input" name="mode">
        <option value="play">Jugar unas horas</option>
        <option value="complete">Completar un juego</option>
      </select></label>
      <label data-for="play">Horas<input class="adm-input" type="number" name="hours" min="0.5" step="0.5" value="2" /></label>
      <label>Duración<select class="adm-input" name="duration">
        ${DURATIONS.map(([value, label]) => html`<option value="${value}" ${value === 'month' ? html`selected` : ''}>${label}</option>`)}
      </select></label>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">Lanzar reto</button>
      </div>
    </form>`);
  const form = m.el.querySelector('form');
  const hoursField = form.querySelector('[data-for="play"]');
  form.elements.mode.addEventListener('change', () => { hoursField.hidden = form.elements.mode.value !== 'play'; });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const options = { genre: form.elements.genre.value, mode: form.elements.mode.value, duration: form.elements.duration.value };
    if (options.mode === 'play') options.hours = Number(form.elements.hours.value);
    try {
      await api('/challenges', jsonRequest('POST', { kind: 'new_genre', options }));
      m.close();
      toast('Reto lanzado');
      await load();
    } catch (err) {
      form.querySelector('.adm-error').textContent = err.message;
    }
  });
}

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  mount(main, html`
    <div class="wl-head">
      <h1 class="pf-title">Retos</h1>
      <button class="pf-btn primary" type="button" id="chNew">Nuevo reto</button>
    </div>
    <p class="pf-sub cal-intro">Objetivos con fecha de fin. Los del grupo los lanza un administrador y cada uno puede salirse; los tuyos los lanzas tú y los ven los demás.</p>
    <div id="chLists"><div class="loading-spinner">Cargando los retos...</div></div>`);
  main.querySelector('#chNew').addEventListener('click', launchGenre);
  main.querySelector('#chLists').addEventListener('click', (e) => {
    const id = e.target.closest('[data-challenge]')?.dataset.challenge;
    const part = e.target.closest('[data-part]');
    if (id && part) change(id, `/participation?joined=${part.dataset.part === 'join'}`, { method: 'PUT' });
    const del = e.target.closest('[data-delete]');
    if (id && del) {
      // the second press confirms
      if (del.dataset.sure) change(id, '', { method: 'DELETE' });
      else {
        del.dataset.sure = '1';
        del.textContent = '¿Seguro? Pulsa otra vez';
      }
    }
  });
  await load();
}
