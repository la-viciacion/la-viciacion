// Session history grouped by game, with expandable sessions and "Seguir".
import { api } from '../../lib/api.js';
import { formatDateTime, formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { platformName } from '../../lib/platforms.js';
import { iconChevron, iconPlay } from '../../ui/icons.js';
import { hasActive } from './timer.js';

const PAGE_SIZE = 8; // games per page

const state = { userId: null, groups: [], total: 0, expanded: new Set() };
let onContinue = () => {};

/** onContinue(group): the user pressed "Seguir" on a game. */
export function initHistory(options) {
  state.userId = options.userId;
  onContinue = options.onContinue;
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
      <div class="history-row ${multi ? 'expandable' : ''}" ${multi ? html`data-action="toggle" role="button" tabindex="0" aria-expanded="${String(open)}"` : ''}>
        ${g.image_url
          ? html`<img src="${g.image_url}" alt="" class="history-thumb" loading="lazy" />`
          : html`<div class="history-thumb history-thumb-placeholder" aria-hidden="true">🎮</div>`}
        <div class="history-main">
          <div class="history-title" title="${name}">${name}</div>
          <div class="history-meta">
            <span>${formatRelative(g.last_played)}</span>
            <span class="dot">·</span>
            <span>${formatDuration(g.total_seconds)}${multi ? ' en total' : ''}</span>
            ${multi ? html`<span class="session-pill">${g.session_count} sesiones</span>` : ''}
            ${g.platforms.map((p) => html`<span class="platform-pill">${platformName(p)}</span>`)}
          </div>
        </div>
        <button class="btn-continue" data-action="continue" data-game-id="${g.game_id}"
                ${hasActive ? html`disabled title="Ya tienes un timer activo"` : ''} aria-label="Seguir jugando a ${name}">
          ${iconPlay()} <span>Seguir</span>
        </button>
        ${multi ? html`<span class="history-chevron" aria-hidden="true">${iconChevron()}</span>` : ''}
      </div>
      ${multi && open ? html`
        <ul class="history-sessions">
          ${g.sessions.map((s) => html`
            <li>
              <span>${formatDateTime(s.start_time)}${s.platform ? ` · ${platformName(s.platform)}` : ''}</span>
              <span class="session-duration">${formatDuration(s.duration_seconds || 0)}</span>
            </li>`)}
          ${hidden > 0 ? html`<li class="session-more">… y ${hidden} sesiones anteriores</li>` : ''}
        </ul>` : ''}
    </article>`;
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
  const row = e.target.closest('[data-action="toggle"]');
  if (row) {
    const id = row.closest('.history-group').dataset.gameId;
    if (state.expanded.has(id)) state.expanded.delete(id);
    else state.expanded.add(id);
    renderHistory();
  }
}
