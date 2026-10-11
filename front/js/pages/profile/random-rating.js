// "Puntuar al azar": the games the player has not rated, one at a time in random order. Saving a rating
// shows the next one by itself; "Omitir" shows another without rating; "Dejar de puntuar" closes it.
// onClose gets the number of games rated, so the list behind can refresh.
import { formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { SCORE_HINT, SCORE_MAX, SCORE_MIN, parseScore, saveScore } from '../../lib/score.js';
import { shuffle } from '../../lib/library-filter.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';

/** `games`: [{ game_id, game_name, image_url, played_time }] without a rating. */
export function openRandomRating({ username, games, onClose }) {
  const queue = shuffle(games);
  const rated = new Set(); // game ids rated in this modal
  let index = 0;
  let message = '';

  const modal = openModal(html`${modalHeader('Puntuar juegos')}<div class="comp-body" id="randBody"></div>`, { onClose: () => onClose?.(rated.size) });
  const body = modal.el.querySelector('#randBody');
  const pending = () => queue.filter((g) => !rated.has(g.game_id));

  // The next game that is still unrated (the same one when it is the only one left); false when none is.
  function advance() {
    for (let step = 1; step <= queue.length; step++) {
      const next = (index + step) % queue.length;
      if (!rated.has(queue[next].game_id)) {
        index = next;
        return true;
      }
    }
    return false;
  }

  function drawDone() {
    mount(body, html`
      <div class="rand-done">${rated.size ? `Listo: has puntuado ${rated.size} ${rated.size === 1 ? 'juego' : 'juegos'}.` : 'No tienes juegos sin puntuar.'}</div>
      <div class="sess-actions"><span class="sess-spacer"></span><button type="button" class="sess-btn primary" data-close>Cerrar</button></div>`);
  }

  function draw() {
    const game = queue[index];
    if (!game) return drawDone();
    const left = pending().length;
    mount(body, html`
      <div class="rand-game">
        ${game.image_url ? html`<img class="rand-cover" src="${game.image_url}" alt="" />` : html`<div class="rand-cover pf-thumb-placeholder" aria-hidden="true">🎮</div>`}
        <div>
          <strong class="rand-name">${game.game_name}</strong>
          <div class="pf-sub">${formatDuration(game.played_time)} jugados</div>
          <div class="pf-sub">${left} ${left === 1 ? 'juego sin puntuar' : 'juegos sin puntuar'}${rated.size ? ` · ${rated.size} puntuados ahora` : ''}</div>
        </div>
      </div>
      <form class="comp-score" id="randForm" novalidate>
        <label>Tu nota (${SCORE_MIN}-${SCORE_MAX})
          <input class="adm-input" type="number" name="score" min="${SCORE_MIN}" max="${SCORE_MAX}" step="1" placeholder="${SCORE_MIN}-${SCORE_MAX}" title="${SCORE_HINT}" />
        </label>
      </form>
      <div class="sess-error" role="alert">${message}</div>
      <div class="sess-actions">
        <button type="button" class="sess-btn" data-close>Dejar de puntuar</button>
        <span class="sess-spacer"></span>
        <button type="button" class="sess-btn" data-skip ${left > 1 ? '' : 'disabled'}>Omitir, ver otro</button>
        <button type="submit" class="sess-btn primary" form="randForm">Guardar nota</button>
      </div>`);
    body.querySelector('input').focus();
  }

  body.addEventListener('click', (e) => {
    if (!e.target.closest('[data-skip]') || e.target.closest('[disabled]')) return;
    message = '';
    advance();
    draw();
  });

  body.addEventListener('submit', async (e) => {
    e.preventDefault();
    const value = parseScore(e.target.elements.score.value);
    if (value == null || Number.isNaN(value)) {
      message = SCORE_HINT;
      return draw();
    }
    const game = queue[index];
    try {
      await saveScore(username, game.game_id, value);
    } catch (err) {
      message = err.message;
      return draw();
    }
    rated.add(game.game_id);
    message = '';
    toast(`${game.game_name}: ${value}`);
    if (!advance()) index = queue.length; // none left
    draw();
  });

  draw();
}
