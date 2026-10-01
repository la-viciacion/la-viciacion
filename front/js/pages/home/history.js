// Latest games played: one row per game. The whole row opens the completion modal (the name is its keyboard target), "Seguir" starts a timer.
// The sessions themselves (and editing them) are in the profile.
import { api } from '../../lib/api.js';
import { formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { platformName } from '../../lib/platforms.js';
import { iconPlay } from '../../ui/icons.js';
import { hasActive } from './timer.js';

const PAGE_SIZE = 8; // games per page

const state = { userId: null, groups: [], total: 0 };
let onContinue = () => {};
let onOpen = () => {};

/** onContinue(group): "Seguir" on a game. onOpen(group): its name was pressed. */
export function initHistory(options) {
  state.userId = options.userId;
  onContinue = options.onContinue;
  onOpen = options.onOpen;
  state.groups = [];
  state.total = 0;
}

export async function loadHistory(reset) {
  const list = document.getElementById('historyList');
  if (!list) return;
  const moreBtn = document.getElementById('historyMoreBtn');
  if (moreBtn) { moreBtn.disabled = true; moreBtn.textContent = 'Cargando...'; }

  try {
    const offset = reset ? 0 : state.groups.length;
    const page = await api(`/timers/history/${state.userId}/grouped?limit=${PAGE_SIZE}&offset=${offset}&sessions_per_game=1`);
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
  return html`
    <article class="history-group" data-game-id="${g.game_id}">
      <div class="history-row" data-action="complete" data-game-id="${g.game_id}">
        ${g.image_url
          ? html`<img src="${g.image_url}" alt="" class="history-thumb" loading="lazy" />`
          : html`<div class="history-thumb history-thumb-placeholder" aria-hidden="true">🎮</div>`}
        <div class="history-main">
          <button class="history-title" title="Marcar ${name} como completado">${name}</button>
          <div class="history-meta">
            <span>${formatRelative(g.last_played)}</span>
            <span class="dot">·</span>
            <span>${formatDuration(g.total_seconds)}${g.session_count > 1 ? ' en total' : ''}</span>
            ${g.completed ? html`<span class="completed-pill">Completado</span>` : ''}
            ${g.session_count > 1 ? html`<span class="session-pill">${g.session_count} sesiones</span>` : ''}
            ${g.platforms.map((p) => html`<span class="platform-pill">${platformName(p)}</span>`)}
          </div>
        </div>
        <button class="btn-continue" data-action="continue" data-game-id="${g.game_id}"
                ${hasActive ? html`disabled title="Ya tienes un timer activo"` : ''} aria-label="Seguir jugando a ${name}">
          ${iconPlay()} <span>Seguir</span>
        </button>
      </div>
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
  const complete = e.target.closest('[data-action="complete"]');
  if (complete) {
    const group = state.groups.find((x) => x.game_id === complete.dataset.gameId);
    if (group) onOpen(group);
  }
}
