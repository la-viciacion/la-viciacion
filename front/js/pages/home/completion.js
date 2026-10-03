// "Marcar completado" from the history: a modal with the library entries of one game (one per
// platform and season). The API decides what can be completed; this only offers it. Dates,
// unmarking and the sessions of a game are in the profile (the games list of the profile summary).
// The rating of the game (1-100, one per game) is edited here too.
import { api, jsonRequest } from '../../lib/api.js';
import { blockedReason } from '../../lib/completion.js';
import { formatDate, formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { SCORE_HINT, SCORE_MAX, SCORE_MIN, parseScore, saveScore } from '../../lib/score.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';

const CONFIRM_MS = 4000;

/** Opens the modal of `game` ({ id, name }) for the user `username`; onChange runs after a completion. */
export async function openCompletion({ username, game, onChange }) {
  const path = `/users/${encodeURIComponent(username)}/library`;
  const modal = openModal(html`${modalHeader(game.name)}<div class="comp-body" id="compBody"><div class="loading-spinner">Cargando...</div></div>`);
  const body = modal.el.querySelector('#compBody');
  let season = new Date().getFullYear();
  let items = [];
  let message = '';
  const score = () => items.find((g) => g.score != null)?.score ?? null; // the same on every entry of the game

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
    ${items.length ? html`
      <form class="comp-score" data-score-form>
        <label>Tu nota
          <input class="adm-input" type="number" name="score" value="${score() ?? ''}" min="${SCORE_MIN}" max="${SCORE_MAX}" step="1" placeholder="1-${SCORE_MAX}" title="${SCORE_HINT}" />
        </label>
        <button type="submit" class="sess-btn primary">Guardar nota</button>
        ${score() == null ? '' : html`<button type="button" class="sess-btn" data-clear-score>Quitar nota</button>`}
      </form>` : ''}
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

  async function rate(value) {
    try {
      await saveScore(username, game.id, value);
      toast(value == null ? 'Nota quitada' : `Nota guardada: ${value}`);
      message = '';
    } catch (err) {
      message = err.message;
    }
    await load();
  }

  body.addEventListener('submit', (e) => {
    const form = e.target.closest('[data-score-form]');
    if (!form) return;
    e.preventDefault();
    const value = parseScore(form.score.value);
    if (value == null || Number.isNaN(value)) {
      message = SCORE_HINT;
      return draw();
    }
    return rate(value);
  });

  // The completion is announced to the group: the first click asks, the second (within 4 s) confirms.
  body.addEventListener('click', async (e) => {
    if (e.target.closest('[data-clear-score]')) return rate(null);
    const button = e.target.closest('[data-complete]');
    if (!button) return;
    if (!button.dataset.armed) {
      button.dataset.armed = '1';
      button.textContent = '¿Seguro? Pulsa otra vez';
      setTimeout(() => {
        if (button.isConnected) { delete button.dataset.armed; button.textContent = 'Marcar completado'; }
      }, CONFIRM_MS);
      return;
    }
    button.disabled = true;
    try {
      await api(`${path}/${button.dataset.complete}/completion`, jsonRequest('PATCH', { completed: true }));
      toast(`«${game.name}» marcado como completado`);
      message = '';
      await onChange();
    } catch (err) {
      message = err.message;
    }
    await load();
  });

  await load();
}
