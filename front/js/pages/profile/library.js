// The games of the profile's summary: those of the season on screen (every season for the total),
// most recently played first, with their completion state.
//   - a pending game of the current season can be marked as completed
//   - any game can be rated (1-100, one rating per game, shown on every entry of it), also right
//     after completing it
//   - a completed game of the current season lets you change the completion date or unmark it;
//     once its season is closed the completion is frozen
//   - a pending game of the current season can be given up (and taken back) with the "Abandonar" (and "Retomar") button of
//     its row. Playing it again resumes it by itself
//   - "Sesiones" lists the sessions of the entry (game and season); those of the current season
//     can be corrected or deleted there
// The API enforces the rules (once per game and season, current season only for completing,
// re-dating and unmarking, date inside the entry's season); the UI only offers what is allowed.
import { api, jsonRequest } from '../../lib/api.js';
import { blockedReason } from '../../lib/completion.js';
import { formatDate, formatDateTime, formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount, raw } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { platformName } from '../../lib/platforms.js';
import { SCORE_HINT, SCORE_MAX, SCORE_MIN, parseScore, saveScore } from '../../lib/score.js';
import * as seasons from '../../lib/seasons.js';
import { iconCalendar, iconCheck, iconClock, iconFlag, iconStar, iconUndo } from '../../ui/icons.js';
import { scoreBadge } from '../../ui/score-badge.js';
import { initSessions, openSessionForm } from '../home/sessions.js';

const PAGE = 15;
const MAX = 100; // API limit per request
const CONFIRM_MS = 4000;

let el;
let username;
let userId;
let onChange;
let season = new Date().getFullYear(); // the running one (what can be completed)
let shown = season; // the one on screen: a year, or seasons.ALL
let items = [];
let total = 0;
let editing = null; // id of the entry whose date is being edited
let rating = null; // id of the entry whose rating is being edited
let sessions = new Map(); // entry id -> its sessions, for the entries that are expanded

const path = (suffix = '') => `/users/${encodeURIComponent(username)}/library${suffix}`;
const seasonQuery = () => (shown === seasons.ALL ? '' : `&season=${shown}`);

function flash(message, ok = false) {
  const msg = el.querySelector('.pf-msg');
  if (!msg) return;
  msg.textContent = message;
  msg.className = `pf-msg ${message ? (ok ? 'ok' : 'err') : ''}`;
}

/** onChange runs after a completion or a session changed (the page refreshes its stats). */
export async function initLibrary(container, options) {
  el = container;
  shown = options.season;
  username = options.username;
  userId = options.userId;
  onChange = options.onChange;
  items = [];
  total = 0;
  editing = null;
  rating = null;
  sessions = new Map();
  initSessions({ userId, onChange: afterSessionChange });
  el.addEventListener('click', onClick);
  el.addEventListener('submit', onSubmit);
  await load(PAGE);
}

/** The summary moved to another season (or to the total): list its games. */
export async function showSeason(value) {
  shown = value;
  items = [];
  total = 0;
  editing = null;
  rating = null;
  sessions = new Map();
  await load(PAGE);
}

// Fetch the first `count` entries again (keeps what was already shown).
async function load(count = Math.max(PAGE, items.length)) {
  try {
    const page = await api(`${path()}?limit=${Math.min(count, MAX)}&offset=0${seasonQuery()}`);
    if (!page) return;
    ({ season, total, items } = page);
    draw();
  } catch (err) {
    mount(el, html`<div class="pf-empty">Error cargando tus juegos: ${err.message}</div>`);
  }
}

async function loadMore() {
  const page = await api(`${path()}?limit=${PAGE}&offset=${items.length}${seasonQuery()}`);
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
  if (g.abandoned) return html`<span class="pf-tag abandoned">Abandonado</span>`;
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

function scoreForm(g) {
  return html`
    <form class="pf-date-form" data-score-form data-id="${g.id}">
      <input class="adm-input pf-score-input" type="number" name="score" value="${g.score ?? ''}" min="${SCORE_MIN}" max="${SCORE_MAX}" step="1" placeholder="1-${SCORE_MAX}" aria-label="Nota de ${g.game_name}" title="${SCORE_HINT}" />
      <button class="pf-btn primary" type="submit">Guardar nota</button>
      ${g.score == null ? '' : html`<button class="pf-btn" type="button" data-action="clear-score" data-id="${g.id}">Quitar nota</button>`}
      <button class="pf-btn" type="button" data-action="cancel-rate">Ahora no</button>
    </form>`;
}

// A row button: an icon plus its label. On a phone only the icon is shown (the label stays for screen readers and
// as a tooltip); a button that asks "¿Seguro?" shows its label again (css: [data-armed]).
function act(action, id, icon, label, { primary = false, title = label, extra = '' } = {}) {
  return html`<button class="pf-btn ${primary ? 'primary' : ''}" data-action="${action}" data-id="${id}" data-label="${label}" title="${title}" aria-label="${title}" ${raw(extra)}>${icon()}<span class="pf-label">${label}</span></button>`;
}

// Abandoning a game (or taking it back) is one more button of the row, with the others.
function abandonButtons(g) {
  return html`${g.can_abandon ? act('abandon', g.id, iconFlag, 'Abandonar') : ''}${g.can_resume ? act('resume', g.id, iconUndo, 'Retomar') : ''}`;
}

function actions(g) {
  const sessionsButton = html`${act('sessions', g.id, iconClock, 'Sesiones', { extra: `aria-expanded="${sessions.has(g.id)}"` })}${act('rate', g.id, iconStar, g.score == null ? 'Puntuar' : 'Cambiar nota')}`;
  if (g.can_complete) {
    return html`${sessionsButton}${act('complete', g.id, iconCheck, 'Marcar completado', { primary: true })}${abandonButtons(g)}`;
  }
  if (!g.completed) {
    return html`${sessionsButton}<button class="pf-btn" disabled title="${blockedReason(g, season)}" aria-label="Marcar completado: ${blockedReason(g, season)}">${iconCheck()}<span class="pf-label">Marcar completado</span></button>${abandonButtons(g)}`;
  }
  if (g.complete_blocked === 'closed_season') return sessionsButton;
  return html`${sessionsButton}${act('edit-date', g.id, iconCalendar, 'Cambiar fecha')}${act('uncomplete', g.id, iconUndo, 'Desmarcar')}`;
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
        <div class="pf-game-title"><strong><a class="game-link" href="${gameHref(g.game_id)}">${g.game_name}</a></strong> ${scoreBadge(g.score)} ${status(g)}</div>
        <div class="pf-sub">
          ${g.platform_name || 'Sin plataforma'} · Temporada ${g.season} · ${formatDuration(g.played_time)}
          ${g.last_played ? ` · Última sesión: ${formatRelative(g.last_played)}` : ''}
        </div>
        ${g.complete_blocked ? html`<div class="pf-lock">🔒 ${blockedReason(g, season)}</div>` : ''}
        ${editing === g.id ? dateForm(g) : ''}
        ${rating === g.id ? scoreForm(g) : ''}
      </div>
      <div class="pf-game-actions">${editing === g.id || rating === g.id ? '' : actions(g)}</div>
      ${sessionList(g)}
    </div>`;
}

function draw() {
  const remaining = total - items.length;
  mount(el, html`
    <div class="pf-card">
      ${items.length ? items.map(row) : html`<div class="pf-empty">No hay juegos en esta selección.</div>`}
      ${remaining > 0 ? html`<button class="pf-btn" data-action="more">Mostrar más (${remaining})</button>` : ''}
      <div class="pf-msg" role="status"></div>
    </div>`);
}

// ── Actions ─────────────────────────────────────────────────
// `askRating`: a game just completed offers to rate it (the form opens on its row).
async function setCompletion(id, body, doneMessage, askRating = false) {
  flash('');
  try {
    await api(`${path(`/${id}/completion`)}`, jsonRequest('PATCH', body));
    editing = null;
    rating = askRating ? id : null;
    await load();
    flash(doneMessage, true);
    await onChange();
  } catch (err) {
    await load(); // re-sync with the server, then say what went wrong
    flash(err.message);
  }
}

// Destructive/announcing buttons: first click asks, second (within 4s) confirms.
const setLabel = (button, text) => { (button.querySelector('.pf-label') || button).textContent = text; };

function armed(button, label) {
  if (button.dataset.armed) return true;
  button.dataset.armed = '1';
  setLabel(button, '¿Seguro? Pulsa otra vez');
  setTimeout(() => {
    if (button.isConnected && button.dataset.armed) {
      delete button.dataset.armed;
      setLabel(button, label);
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

async function setAbandoned(id, abandoned) {
  flash('');
  const name = items.find((g) => g.id === id)?.game_name;
  try {
    await api(path(`/${id}/abandoned`), jsonRequest('PATCH', { abandoned }));
    await load();
    flash(abandoned ? `«${name}» marcado como abandonado. Si vuelves a jugarlo, se retoma solo` : `«${name}» retomado`, true);
  } catch (err) {
    await load();
    flash(err.message);
  }
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
      setLabel(button, 'Completando…');
      return setCompletion(id, { completed: true }, `«${items.find((g) => g.id === id)?.game_name}» marcado como completado`, true);
    case 'uncomplete':
      if (!armed(button, button.dataset.label)) return;
      button.disabled = true;
      return setCompletion(id, { completed: false }, 'Marcado como no completado');
    case 'abandon':
      return setAbandoned(id, true);
    case 'resume':
      return setAbandoned(id, false);
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
      rating = null;
      return draw();
    case 'cancel-date':
      editing = null;
      return draw();
    case 'rate':
      rating = id;
      editing = null;
      return draw();
    case 'cancel-rate':
      rating = null;
      return draw();
    case 'clear-score':
      return rate(id, null);
  }
}

async function rate(id, score) {
  flash('');
  const entry = items.find((g) => g.id === id);
  try {
    await saveScore(username, entry.game_id, score);
    rating = null;
    await load();
    flash(score == null ? 'Nota quitada' : `Nota guardada: ${score}`, true);
  } catch (err) {
    flash(err.message);
  }
}

function onSubmit(e) {
  const form = e.target.closest('.pf-date-form');
  if (!form) return;
  e.preventDefault();
  if (form.dataset.scoreForm !== undefined) {
    const score = parseScore(form.score.value);
    if (score == null || Number.isNaN(score)) return flash(SCORE_HINT);
    return rate(Number(form.dataset.id), score);
  }
  const date = form.date.value;
  if (!date) return flash('Elige una fecha');
  return setCompletion(Number(form.dataset.id), { completed: true, completed_date: date }, 'Fecha actualizada');
}
