// "Marcar completado" from the history: a modal with the library entries of one game (one per
// platform and season). The API decides what can be completed; this only offers it. Dates,
// unmarking and the sessions of a game are in the profile (the games list of the profile summary).
// Once a game is completed, a second modal (rating.js) offers to rate it.
import { api, jsonRequest } from '../../lib/api.js';
import { blockedReason } from '../../lib/completion.js';
import { formatDate, formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { scoreBadge } from '../../ui/score-badge.js';
import { openRating } from './rating.js';

/** Opens the modal of `game` ({ id, name }) for the user `username`; onChange runs after a completion. */
export async function openCompletion({ username, game, onChange }) {
  const path = `/users/${encodeURIComponent(username)}/library`;
  const modal = openModal(html`${modalHeader(html`${game.name} ${scoreBadge(game.score)}`)}<div class="comp-body" id="compBody"><div class="loading-spinner">Cargando...</div></div>`);
  const body = modal.el.querySelector('#compBody');
  let season = new Date().getFullYear();
  let items = [];
  let message = '';

  const status = (g) => {
    if (g.completed) return html`<span class="pf-tag done">Completado${g.completed_date ? ` el ${formatDate(g.completed_date)}` : ''}</span>`;
    return g.complete_blocked === 'closed_season' ? html`<span class="pf-tag muted">Sin completar</span>` : html`<span class="pf-tag">En curso</span>`;
  };

  const action = (g) => {
    if (g.can_complete) return html`<button class="sess-btn primary" data-complete="${g.id}">Marcar completado</button>`;
    if (g.completed) return '';
    return html`<div class="pf-lock">🔒 ${blockedReason(g, season)}</div>`;
  };

  const draw = () => mount(body, html`
    <div class="comp-list">
      ${items.length ? items.map((g) => html`
        <div class="comp-entry">
          <div>
            <div><strong>${g.platform_name || 'Sin plataforma'}</strong> · Temporada ${g.season} ${status(g)}</div>
            <div class="pf-sub">${formatDuration(g.played_time)} jugados</div>
          </div>
          ${action(g)}
        </div>`) : html`<div class="pf-empty">Este juego no está en tu biblioteca.</div>`}
    </div>
    <div class="sess-error" role="alert">${message}</div>
    <div class="sess-actions">
      <a class="pf-sub" href="#/profile/resumen" data-close>Ver mis juegos y sesiones</a>
      <span class="sess-spacer"></span>
      <button type="button" class="sess-btn" data-close>Cerrar</button>
    </div>`);

  async function load() {
    try {
      const page = await api(`${path}?game_id=${encodeURIComponent(game.id)}&limit=100`);
      if (!page) return;
      ({ season, items } = page);
      draw();
    } catch (err) {
      mount(body, html`<div class="sess-error" role="alert">${err.message}</div>`);
    }
  }

  // The completion is announced to the group, but opening this modal was already the question: one click completes.
  body.addEventListener('click', async (e) => {
    const button = e.target.closest('[data-complete]');
    if (!button) return;
    button.disabled = true;
    try {
      await api(`${path}/${button.dataset.complete}/completion`, jsonRequest('PATCH', { completed: true }));
      toast(`«${game.name}» marcado como completado`);
      message = '';
      const current = items.find((g) => g.score != null)?.score ?? null; // the same on every entry of the game
      openRating({ username, game, current });
      await onChange();
    } catch (err) {
      message = err.message;
    }
    await load();
  });

  await load();
}
