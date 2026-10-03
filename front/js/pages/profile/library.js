// "Mis juegos": every game of the user (all seasons), most recently played
// first, with its completion state.
//   - a pending game of the current season can be marked as completed
//   - a completed game of the current season lets you change the completion date or unmark it;
//     once its season is closed the completion is frozen
//   - "Sesiones" lists the sessions of the entry (game and season); those of the current season
//     can be corrected or deleted there
// The API enforces the rules (once per game and season, current season only for completing,
// re-dating and unmarking, date inside the entry's season); the UI only offers what is allowed.
import { api, jsonRequest } from '../../lib/api.js';
import { blockedReason } from '../../lib/completion.js';
import { formatDate, formatDateTime, formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { platformName } from '../../lib/platforms.js';
import { initSessions, openSessionForm } from '../home/sessions.js';

const PAGE = 15;
const MAX = 100; // API limit per request
const CONFIRM_MS = 4000;

let el;
let username;
let userId;
let onChange;
let season = new Date().getFullYear();
let items = [];
let total = 0;
let editing = null; // id of the entry whose date is being edited
let sessions = new Map(); // entry id -> its sessions, for the entries that are expanded

const path = (suffix = '') => `/users/${encodeURIComponent(username)}/library${suffix}`;

function flash(message, ok = false) {
  const msg = el.querySelector('.pf-msg');
  if (!msg) return;
  msg.textContent = message;
  msg.className = `pf-msg ${message ? (ok ? 'ok' : 'err') : ''}`;
}

/** onChange runs after a completion or a session changed (the page refreshes its stats). */
export async function initLibrary(container, options) {
  el = container;
  username = options.username;
  userId = options.userId;
  onChange = options.onChange;
  items = [];
  total = 0;
  editing = null;
  sessions = new Map();
  initSessions({ userId, onChange: afterSessionChange });
  el.addEventListener('click', onClick);
  el.addEventListener('submit', onSubmit);
  await load(PAGE);
}

// Fetch the first `count` entries again (keeps what was already shown).
async function load(count = Math.max(PAGE, items.length)) {
  try {
    const page = await api(`${path()}?limit=${Math.min(count, MAX)}&offset=0`);
    if (!page) return;
    ({ season, total, items } = page);
    draw();
  } catch (err) {
    mount(el, html`<div class="pf-empty">Error cargando tus juegos: ${err.message}</div>`);
  }
}

async function loadMore() {
  const page = await api(`${path()}?limit=${PAGE}&offset=${items.length}`);
  if (!page) return;
  items = items.concat(page.items);
  total = page.total;
  draw();
}

// ── Templates ───────────────────────────────────────────────
const thumb = (g) => (g.image_url
  ? html`<img src="${g.image_url}" alt="" class="pf-thumb" loading="lazy" />`
  : html`<div class="pf-thumb pf-thumb-placeholder" aria-hidden="true">🎮</div>`);

function status(g) {
  if (g.completed) {
    return html`<span class="pf-tag done">Completado${g.completed_date ? ` el ${formatDate(g.completed_date)}` : ''}</span>`;
  }
  // an unfinished game of a closed season is no longer "in progress"
  return g.complete_blocked === 'closed_season'
    ? html`<span class="pf-tag muted">Sin completar</span>`
    : html`<span class="pf-tag">En curso</span>`;
}

// Latest day a completion may be dated: today, or the end of a past season.
const maxDate = (g) => {
  const today = new Date().toLocaleDateString('sv-SE');
  return g.season === season ? today : `${g.season}-12-31`;
};

function dateForm(g) {
  const min = g.started_date && g.started_date.startsWith(String(g.season)) ? g.started_date : `${g.season}-01-01`;
  return html`
    <form class="pf-date-form" data-id="${g.id}">
      <input class="adm-input" type="date" name="date" value="${g.completed_date || ''}" min="${min}" max="${maxDate(g)}" required />
      <button class="pf-btn primary" type="submit">Guardar</button>
      <button class="pf-btn" type="button" data-action="cancel-date">Cancelar</button>
    </form>`;
}

function actions(g) {
  const sessionsButton = html`<button class="pf-btn" data-action="sessions" data-id="${g.id}" aria-expanded="${String(sessions.has(g.id))}">Sesiones</button>`;
  if (g.can_complete) {
    return html`${sessionsButton}<button class="pf-btn primary" data-action="complete" data-id="${g.id}" data-label="Marcar completado">Marcar completado</button>`;
  }
  if (!g.completed) {
    return html`${sessionsButton}<button class="pf-btn" disabled title="${blockedReason(g, season)}">Marcar completado</button>`;
  }
  if (g.complete_blocked === 'closed_season') return sessionsButton;
  return html`
    ${sessionsButton}
    <button class="pf-btn" data-action="edit-date" data-id="${g.id}">Cambiar fecha</button>
    <button class="pf-btn" data-action="uncomplete" data-id="${g.id}" data-label="Desmarcar">Desmarcar</button>`;
}

// The sessions of an entry; the API only lets you change those of the running season.
function sessionList(g) {
  const list = sessions.get(g.id);
  if (!list) return '';
  if (!list.length) return html`<div class="pf-sub">Sin sesiones registradas.</div>`;
  return html`
    <ul class="pf-sessions">
      ${list.map((s) => html`
        <li>
          <span>${formatDateTime(s.start_time)}${s.platform ? ` · ${platformName(s.platform)}` : ''}</span>
          <span class="session-end">
            <span class="session-duration">${formatDuration(s.duration_seconds || 0)}</span>
            ${g.season === season ? html`<button class="btn-session" data-action="edit-session" data-id="${g.id}" data-timer-id="${s.id}" aria-label="Editar sesión">Editar</button>` : ''}
          </span>
        </li>`)}
    </ul>`;
}

function row(g) {
  return html`
    <div class="pf-game ${g.complete_blocked ? 'locked' : ''}" data-id="${g.id}">
      ${thumb(g)}
      <div class="pf-row-main">
        <div class="pf-game-title"><strong>${g.game_name}</strong> ${status(g)}</div>
        <div class="pf-sub">
          ${g.platform_name || 'Sin plataforma'} · Temporada ${g.season} · ${formatDuration(g.played_time)}
          ${g.last_played ? ` · Última sesión: ${formatRelative(g.last_played)}` : ''}
        </div>
        ${g.complete_blocked ? html`<div class="pf-lock">🔒 ${blockedReason(g, season)}</div>` : ''}
        ${editing === g.id ? dateForm(g) : ''}
      </div>
      <div class="pf-game-actions">${editing === g.id ? '' : actions(g)}</div>
      ${sessionList(g)}
    </div>`;
}

function draw() {
  const remaining = total - items.length;
  mount(el, html`
    <div class="pf-card">
      ${items.length ? items.map(row) : html`<div class="pf-empty">Todavía no has jugado a ningún juego.</div>`}
      ${remaining > 0 ? html`<button class="pf-btn" data-action="more">Mostrar más (${remaining})</button>` : ''}
      <div class="pf-msg" role="status"></div>
    </div>`);
}

// ── Actions ─────────────────────────────────────────────────
async function setCompletion(id, body, doneMessage) {
  flash('');
  try {
    await api(`${path(`/${id}/completion`)}`, jsonRequest('PATCH', body));
    editing = null;
    await load();
    flash(doneMessage, true);
    await onChange();
  } catch (err) {
    await load(); // re-sync with the server, then say what went wrong
    flash(err.message);
  }
}

// Destructive/announcing buttons: first click asks, second (within 4s) confirms.
function armed(button, label) {
  if (button.dataset.armed) return true;
  button.dataset.armed = '1';
  button.textContent = '¿Seguro? Pulsa otra vez';
  setTimeout(() => {
    if (button.isConnected && button.dataset.armed) {
      delete button.dataset.armed;
      button.textContent = label;
    }
  }, CONFIRM_MS);
  return false;
}

async function loadSessions(entry) {
  const all = await api(`/timers/history/${userId}?game_id=${encodeURIComponent(entry.game_id)}&limit=500`);
  sessions.set(entry.id, (all || []).filter((s) => !s.is_active && s.season === entry.season));
}

// A session was edited, added or deleted: reload the open lists and the numbers of the entries.
async function afterSessionChange() {
  await Promise.all([...sessions.keys()].map((id) => loadSessions(items.find((g) => g.id === id))));
  await load();
  await onChange();
}

async function toggleSessions(entry) {
  if (sessions.has(entry.id)) sessions.delete(entry.id);
  else await loadSessions(entry);
  draw();
}

async function onClick(e) {
  const button = e.target.closest('[data-action]');
  if (!button) return;
  const id = Number(button.dataset.id);

  switch (button.dataset.action) {
    case 'more':
      button.disabled = true;
      return loadMore().catch((err) => { button.disabled = false; flash(err.message); });
    case 'complete':
      if (!armed(button, button.dataset.label)) return;
      button.disabled = true;
      button.textContent = 'Completando…';
      return setCompletion(id, { completed: true }, `«${items.find((g) => g.id === id)?.game_name}» marcado como completado`);
    case 'uncomplete':
      if (!armed(button, button.dataset.label)) return;
      button.disabled = true;
      return setCompletion(id, { completed: false }, 'Marcado como no completado');
    case 'sessions':
      return toggleSessions(items.find((g) => g.id === id)).catch((err) => flash(err.message));
    case 'edit-session': {
      const entry = items.find((g) => g.id === id);
      const session = sessions.get(id)?.find((s) => String(s.id) === button.dataset.timerId);
      if (entry && session) openSessionForm({ game: { id: entry.game_id, name: entry.game_name }, session });
      return;
    }
    case 'edit-date':
      editing = id;
      return draw();
    case 'cancel-date':
      editing = null;
      return draw();
  }
}

function onSubmit(e) {
  const form = e.target.closest('.pf-date-form');
  if (!form) return;
  e.preventDefault();
  const date = form.date.value;
  if (!date) return flash('Elige una fecha');
  return setCompletion(Number(form.dataset.id), { completed: true, completed_date: date }, 'Fecha actualizada');
}
