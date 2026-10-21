// The games of a player's library, as a list of rows with their buttons. Two lists of the profile use it:
//   - Resumen: the games of the season on screen (every season for the total), most recently played first
//   - Mis juegos (`filterable`): every game of every season, with filters and the random rating
// What a row offers:
//   - a pending game of the current season can be marked as completed
//   - any game can be rated (1-100, one rating per game, shown on every entry of it), also right
//     after completing it
//   - a completed game of the current season lets you change the completion date or unmark it;
//     once its season is closed the completion is frozen
//   - a pending game of the current season can be given up (and taken back) with the "Abandonar" (and "Retomar") button of
//     its row. Playing it again resumes it by itself
//   - a game played on several platforms in a season is one row (the API groups its entries); the buttons act on
//     the entry the API picked to stand for them
//   - "Sesiones" lists the sessions of the entry (game and season); those of the current season
//     can be corrected or deleted there
// The API enforces the rules (once per game and season, current season only for completing,
// re-dating and unmarking, date inside the entry's season); the UI only offers what is allowed.
import { api, jsonRequest } from '../../lib/api.js';
import { blockedReason } from '../../lib/completion.js';
import { formatDate, formatDateTime, formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount, raw } from '../../lib/html.js';
import { NO_FILTERS, NO_PLATFORM, STATES, entryPlatforms, entryState, filterEntries, unratedGames } from '../../lib/library-filter.js';
import { gameHref } from '../../lib/links.js';
import { platformName } from '../../lib/platforms.js';
import { SCORE_HINT, SCORE_MAX, SCORE_MIN, parseScore, saveScore } from '../../lib/score.js';
import * as seasons from '../../lib/seasons.js';
import { iconCalendar, iconCircleCheck, iconClock, iconFlag, iconStar, iconUndo } from '../../ui/icons.js';
import { scoreBadge } from '../../ui/score-badge.js';
import { initSessions, openSessionForm } from '../home/sessions.js';
import { openRandomRating } from './random-rating.js';

const PAGE = 15;
const PAGE_ALL = 30; // the full list shows more at a time
const MAX = 100; // API limit per request
const CONFIRM_MS = 4000;

// ── Templates that do not depend on the list ────────────────
const thumb = (g) => (g.image_url
  ? html`<img src="${g.image_url}" alt="" class="pf-thumb" loading="lazy" />`
  : html`<div class="pf-thumb pf-thumb-placeholder" aria-hidden="true">🎮</div>`);

function status(g) {
  switch (entryState(g)) {
    case 'completed':
      return html`<span class="pf-tag done">Completado${g.completed_date ? ` el ${formatDate(g.completed_date)}` : ''}</span>`;
    case 'abandoned':
      return html`<span class="pf-tag abandoned">Abandonado</span>`;
    // an unfinished game of a closed season is no longer "in progress"
    case 'unfinished':
      return html`<span class="pf-tag muted">Sin completar</span>`;
    default:
      return html`<span class="pf-tag">En curso</span>`;
  }
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
// as a tooltip); a button that asks to confirm shows its question again (css: [data-armed]), naming the action
// because the icon alone does not say which of the buttons is asking.
function act(action, id, icon, label, { primary = false, title = label, extra = '', confirm = '' } = {}) {
  return html`<button class="pf-btn ${primary ? 'primary' : ''}" data-action="${action}" data-id="${id}" data-label="${label}" data-confirm="${confirm}" title="${title}" aria-label="${title}" ${raw(extra)}>${icon()}<span class="pf-label">${label}</span></button>`;
}

// Abandoning a game (or taking it back) is one more button of the row, with the others.
function abandonButtons(g) {
  return html`${g.can_abandon ? act('abandon', g.id, iconFlag, 'Abandonar', { confirm: '¿Abandonar?' }) : ''}${g.can_resume ? act('resume', g.id, iconUndo, 'Retomar', { confirm: '¿Retomar?' }) : ''}`;
}

// Destructive/announcing buttons: first click asks, second (within 4s) confirms.
const setLabel = (button, text) => { (button.querySelector('.pf-label') || button).textContent = text; };

function armed(button, label) {
  if (button.dataset.armed) return true;
  button.dataset.armed = '1';
  setLabel(button, button.dataset.confirm || '¿Seguro?');
  setTimeout(() => {
    if (button.isConnected && button.dataset.armed) {
      delete button.dataset.armed;
      setLabel(button, label);
    }
  }, CONFIRM_MS);
  return false;
}

const select = (key, label, options, value) => html`
  <select class="adm-input" data-filter="${key}" aria-label="${label}">
    <option value="">${label}: todos</option>
    ${options.map(([v, text]) => html`<option value="${v}" ${String(v) === String(value) ? 'selected' : ''}>${text}</option>`)}
  </select>`;

/**
 * A list of the library of `username`. Options: season (a year, or seasons.ALL), filterable, userId,
 * onChange (runs after a completion or a session changed: the page refreshes its stats).
 * Returns { init, showSeason, reload }.
 */
export function createLibrary(el, options) {
  const { username, userId, onChange, filterable = false } = options;
  const step = filterable ? PAGE_ALL : PAGE;
  let season = new Date().getFullYear(); // the running one (what can be completed)
  let shown = options.season; // the one on screen: a year, or seasons.ALL
  let items = [];
  let total = 0;
  let visible = step; // how many rows of the (filtered) list are drawn
  let filters = { ...NO_FILTERS };
  let editing = null; // id of the entry whose date is being edited
  let rating = null; // id of the entry whose rating is being edited
  let sessions = new Map(); // entry id -> its sessions, for the entries that are expanded
  let list = el; // where the rows go: the whole element, or below the filters

  const path = (suffix = '') => `/users/${encodeURIComponent(username)}/library${suffix}`;
  const seasonQuery = () => (shown === seasons.ALL ? '' : `&season=${shown}`);

  function flash(message, ok = false) {
    const msg = list.querySelector('.pf-msg');
    if (!msg) return;
    msg.textContent = message;
    msg.className = `pf-msg ${message ? (ok ? 'ok' : 'err') : ''}`;
  }

  function reset() {
    items = [];
    total = 0;
    visible = step;
    editing = null;
    rating = null;
    sessions = new Map();
  }

  // The first `count` entries (all of them for the full list), fetched page by page.
  async function fetchEntries(count) {
    const out = [];
    let page;
    do {
      page = await api(`${path()}?limit=${Math.min(count - out.length, MAX)}&offset=${out.length}${seasonQuery()}`);
      if (!page) return null;
      out.push(...page.items);
    } while (out.length < Math.min(count, page.total) && page.items.length);
    return { ...page, items: out };
  }

  // Fetch the first `count` entries again (keeps what was already shown).
  async function load(count = filterable ? Infinity : Math.max(PAGE, items.length)) {
    try {
      const page = await fetchEntries(count);
      if (!page) return;
      ({ season, total, items } = page);
      if (filterable) drawBar();
      draw();
    } catch (err) {
      mount(list, html`<div class="pf-empty">Error cargando tus juegos: ${err.message}</div>`);
    }
  }

  async function init() {
    if (filterable) {
      mount(el, html`<div class="adm-toolbar pf-lib-bar"></div><div class="pf-lib-list"></div>`);
      list = el.querySelector('.pf-lib-list');
      el.addEventListener('input', onFilter);
    }
    el.addEventListener('click', onClick);
    el.addEventListener('submit', onSubmit);
    await load();
  }

  /** The summary moved to another season (or to the total): list its games. */
  async function showSeason(value) {
    shown = value;
    reset();
    await load();
  }

  /** Another list changed something: fetch again, keeping what is open. */
  const reload = () => load();

  // ── Filters (the full list) ───────────────────────────────
  function drawBar() {
    const years = [...new Set(items.map((g) => g.season))].sort((a, b) => b - a);
    const platforms = new Map(items.flatMap((g) => (entryPlatforms(g).length ? entryPlatforms(g) : [{ id: NO_PLATFORM, name: 'Sin plataforma' }])
      .map((p) => [String(p.id), p.name])));
    const pending = unratedGames(items).length;
    mount(el.querySelector('.pf-lib-bar'), html`
      <input class="adm-input" type="search" data-filter="q" value="${filters.q}" placeholder="Buscar juego" aria-label="Buscar juego" />
      ${select('season', 'Temporada', years.map((y) => [y, y]), filters.season)}
      ${select('state', 'Estado', STATES, filters.state)}
      ${select('rated', 'Nota', [['yes', 'Puntuados'], ['no', 'Sin puntuar']], filters.rated)}
      ${select('platform', 'Plataforma', [...platforms], filters.platform)}
      <span class="adm-spacer"></span>
      <button class="pf-btn primary" type="button" data-action="random-rate" ${pending ? '' : 'disabled'}>${iconStar()}<span>Puntuar al azar (${pending})</span></button>`);
  }

  function onFilter(e) {
    const key = e.target.dataset?.filter;
    if (!key) return;
    filters = { ...filters, [key]: e.target.value };
    visible = step;
    draw();
  }

  // ── Templates ─────────────────────────────────────────────
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
    const sessionsButton = html`${act('sessions', g.id, iconClock, 'Sesiones', { extra: `aria-expanded="${sessions.has(g.id)}"` })}${act('rate', g.id, iconStar, g.score == null ? 'Puntuar' : 'Cambiar nota')}`;
    if (g.can_complete) {
      return html`${sessionsButton}${act('complete', g.id, () => iconCircleCheck(18), 'Marcar completado', { confirm: '¿Completar?' })}${abandonButtons(g)}`;
    }
    if (!g.completed) {
      return html`${sessionsButton}<button class="pf-btn" disabled title="${blockedReason(g, season)}" aria-label="Marcar completado: ${blockedReason(g, season)}">${iconCircleCheck(18)}<span class="pf-label">Marcar completado</span></button>${abandonButtons(g)}`;
    }
    if (g.complete_blocked === 'closed_season') return sessionsButton;
    return html`${sessionsButton}${act('edit-date', g.id, iconCalendar, 'Cambiar fecha')}${act('uncomplete', g.id, iconUndo, 'Desmarcar', { confirm: '¿Desmarcar?' })}`;
  }

  // The sessions of an entry; the API only lets you change those of the running season.
  function sessionList(g) {
    const entrySessions = sessions.get(g.id);
    if (!entrySessions) return '';
    if (!entrySessions.length) return html`<div class="pf-sub">Sin sesiones registradas.</div>`;
    return html`
      <ul class="pf-sessions">
        ${entrySessions.map((s) => html`
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
            ${entryPlatforms(g).map((p) => p.name).join(' · ') || 'Sin plataforma'} · Temporada ${g.season} · ${formatDuration(g.played_time)}
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
    const matching = filterable ? filterEntries(items, filters) : items;
    const remaining = filterable ? matching.length - Math.min(visible, matching.length) : total - items.length;
    const count = filterable ? html`<div class="pf-sub" role="status">${matching.length === items.length ? `${items.length} juegos` : `${matching.length} de ${items.length} juegos`}</div>` : '';
    mount(list, html`
      <div class="pf-card">
        ${count}
        ${matching.length ? matching.slice(0, filterable ? visible : matching.length).map(row) : html`<div class="pf-empty">No hay juegos en esta selección.</div>`}
        ${remaining > 0 ? html`<button class="pf-btn" data-action="more">Mostrar más (${remaining})</button>` : ''}
        <div class="pf-msg" role="status"></div>
      </div>`);
  }

  async function loadMore() {
    if (filterable) {
      visible += step;
      return draw();
    }
    const page = await api(`${path()}?limit=${PAGE}&offset=${items.length}${seasonQuery()}`);
    if (!page) return;
    items = items.concat(page.items);
    total = page.total;
    draw();
  }

  // ── Actions ───────────────────────────────────────────────
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

  // The random rating: the games without a rating, one after another; the list is refreshed when it closes.
  function rateAtRandom() {
    openRandomRating({
      username,
      games: unratedGames(items),
      onClose: async (rated) => {
        if (!rated) return;
        await load();
        await onChange();
      },
    });
  }

  async function onClick(e) {
    const button = e.target.closest('[data-action]');
    if (!button) return;
    const id = Number(button.dataset.id);

    switch (button.dataset.action) {
      case 'more':
        button.disabled = true;
        return loadMore().catch((err) => { button.disabled = false; flash(err.message); });
      case 'random-rate':
        return rateAtRandom();
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
        if (!armed(button, button.dataset.label)) return;
        button.disabled = true;
        return setAbandoned(id, true);
      case 'resume':
        if (!armed(button, button.dataset.label)) return;
        button.disabled = true;
        return setAbandoned(id, false);
      case 'sessions':
        return toggleSessions(items.find((g) => g.id === id)).catch((err) => flash(err.message));
      case 'edit-session': {
        const entry = items.find((g) => g.id === id);
        const session = sessions.get(id)?.find((s) => String(s.id) === button.dataset.timerId);
        // the session form reports to whoever asked last, and two lists share it
        initSessions({ userId, onChange: afterSessionChange });
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

  return { init, showSeason, reload };
}
