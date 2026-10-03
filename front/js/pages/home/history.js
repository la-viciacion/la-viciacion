// Latest games played: one row per game. Pressing the row unfolds its latest sessions (editable), the play button
// starts a timer and the check button opens the completion modal.
import { api } from '../../lib/api.js';
import { formatDateTime, formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { platformName } from '../../lib/platforms.js';
import { iconCheck, iconChevron, iconPlay } from '../../ui/icons.js';
import { scoreBadge } from '../../ui/score-badge.js';
import { hasActive } from './timer.js';

const PAGE_SIZE = 8; // games per page

const state = { userId: null, groups: [], total: 0, expanded: new Set() };
let onContinue = () => {};
let onComplete = () => {};
let onEditSession = () => {};

/** onContinue(group): play on a game. onComplete(group): its check button. onEditSession(group, session): "Editar" on a session. */
export function initHistory(options) {
  state.userId = options.userId;
  onContinue = options.onContinue;
  onComplete = options.onComplete;
  onEditSession = options.onEditSession;
  state.groups = [];
  state.total = 0;
  state.expanded = new Set();
}

export async function loadHistory(reset) {
  const list = document.getElementById('historyList');
  if (!list) return;
  const moreBtn = document.getElementById('historyMoreBtn');
  if (moreBtn) { moreBtn.disabled = true; moreBtn.textContent = 'Cargando...'; }

  try {
    const offset = reset ? 0 : state.groups.length;
    const page = await api(`/timers/history/${state.userId}/grouped?limit=${PAGE_SIZE}&offset=${offset}`);
    if (!page) return;
    state.total = page.total_games;
    state.groups = reset ? page.groups : state.groups.concat(page.groups);
  } catch (err) {
    mount(list, html`<div class="empty-state"><span>⚠️</span>Error cargando el historial: ${err.message}</div>`);
    return;
  }
  renderHistory();
}

function renderHistory() {
  const list = document.getElementById('historyList');
  const more = document.getElementById('historyMore');
  if (!list) return;

  if (!state.groups.length) {
    mount(list, html`<div class="empty-state"><span>⏱️</span>Aún no tienes sesiones registradas. ¡Inicia tu primer timer!</div>`);
    mount(more, html``);
    return;
  }

  mount(list, html`${state.groups.map(groupRow)}`);
  const remaining = state.total - state.groups.length;
  mount(more, remaining > 0 ? html`<button class="btn-load-more" id="historyMoreBtn">Mostrar más (${remaining})</button>` : html``);
}

function groupRow(g) {
  const name = g.game_name || g.game_id;
  const multi = g.session_count > 1;
  const open = state.expanded.has(g.game_id);
  const hidden = g.session_count - g.sessions.length;

  return html`
    <article class="history-group ${open ? 'open' : ''}" data-game-id="${g.game_id}">
      <div class="history-row" data-action="toggle" role="button" tabindex="0" aria-expanded="${String(open)}">
        ${g.image_url
          ? html`<img src="${g.image_url}" alt="" class="history-thumb" loading="lazy" />`
          : html`<div class="history-thumb history-thumb-placeholder" aria-hidden="true">🎮</div>`}
        <div class="history-main">
          <div class="history-title" title="${name}"><span class="history-name">${name}</span>${scoreBadge(g.score)}</div>
          <div class="history-meta">
            <span>${formatRelative(g.last_played)}</span>
            <span class="dot">·</span>
            <span>${formatDuration(g.total_seconds)}${multi ? ' en total' : ''}</span>
            ${multi ? html`<span class="session-pill">${g.session_count} sesiones</span>` : ''}
            ${g.platforms.map((p) => html`<span class="platform-pill">${platformName(p)}</span>`)}
          </div>
        </div>
        <button class="btn-continue ${g.completed ? 'done' : ''}" data-action="complete" data-game-id="${g.game_id}"
                title="${g.completed ? 'Completado esta temporada' : 'Marcar como completado'}" aria-label="${g.completed ? `${name} ya está completado` : `Marcar ${name} como completado`}">${iconCheck()}</button>
        <button class="btn-continue" data-action="continue" data-game-id="${g.game_id}"
                ${hasActive ? html`disabled title="Ya tienes un timer activo"` : html`title="Seguir jugando"`} aria-label="Seguir jugando a ${name}">${iconPlay()}</button>
        <span class="history-chevron" aria-hidden="true">${iconChevron()}</span>
      </div>
      ${open ? html`
        <ul class="history-sessions">
          ${g.sessions.map((s) => html`
            <li>
              <span>${formatDateTime(s.start_time)}${s.platform ? ` · ${platformName(s.platform)}` : ''}</span>
              <span class="session-end">
                <span class="session-duration">${formatDuration(s.duration_seconds || 0)}</span>
                <button class="btn-session" data-action="edit-session" data-game-id="${g.game_id}" data-timer-id="${s.id}" aria-label="Editar sesión">Editar</button>
              </span>
            </li>`)}
          <li class="session-more"><a class="game-link" href="${gameHref(g.game_id)}">Ver la ficha del juego</a></li>
          ${hidden > 0 ? html`<li class="session-more">… y ${hidden} sesiones anteriores
            <button class="btn-session" data-action="all-sessions" data-game-id="${g.game_id}">Ver todas</button></li>` : ''}
        </ul>` : ''}
    </article>`;
}

// The history keeps the latest sessions per game; "Ver todas" loads the rest.
async function loadAllSessions(gameId) {
  const group = state.groups.find((x) => x.game_id === gameId);
  if (!group) return;
  const all = await api(`/timers/history/${state.userId}?game_id=${encodeURIComponent(gameId)}&limit=500`);
  if (all) {
    group.sessions = all.filter((s) => !s.is_active);
    renderHistory();
  }
}

/** Delegated click handler for #historyList and #historyMore. */
export function onHistoryClick(e) {
  if (e.target.closest('#historyMoreBtn')) return loadHistory(false);

  const cont = e.target.closest('[data-action="continue"]');
  if (cont) {
    if (cont.disabled) return;
    // Reuse the info of the most recent session (same platform).
    const group = state.groups.find((x) => x.game_id === cont.dataset.gameId);
    if (group) onContinue(group);
    return;
  }
  const complete = e.target.closest('[data-action="complete"]');
  if (complete) {
    const group = state.groups.find((x) => x.game_id === complete.dataset.gameId);
    if (group) onComplete(group);
    return;
  }
  const edit = e.target.closest('[data-action="edit-session"]');
  if (edit) {
    const group = state.groups.find((x) => x.game_id === edit.dataset.gameId);
    const session = group?.sessions.find((x) => String(x.id) === edit.dataset.timerId);
    if (group && session) onEditSession(group, session);
    return;
  }
  const all = e.target.closest('[data-action="all-sessions"]');
  if (all) return loadAllSessions(all.dataset.gameId);

  const row = e.target.closest('[data-action="toggle"]');
  if (row) toggle(row.closest('.history-group').dataset.gameId);
}

/** Keyboard: Enter/Space on the focused row unfolds it (the buttons inside keep their own behaviour). */
export function onHistoryKey(e) {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const row = e.target.closest('[data-action="toggle"]');
  if (row !== e.target) return;
  e.preventDefault();
  toggle(row.closest('.history-group').dataset.gameId);
}

function toggle(gameId) {
  if (state.expanded.has(gameId)) state.expanded.delete(gameId);
  else state.expanded.add(gameId);
  renderHistory();
}
