// The question that follows a completion in the history: "do you want to rate this game?".
// Saving rates it (1-100, one rating per game); "Ahora no" leaves it as it was. The rating can
// also be changed or removed later from the games list of the profile.
import { html, mount } from '../../lib/html.js';
import { SCORE_HINT, SCORE_MAX, SCORE_MIN, parseScore, saveScore } from '../../lib/score.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';

/** `current` is the rating the game already has (null if none); onSaved runs after a rating is stored. */
export function openRating({ username, game, current = null, onSaved }) {
  const modal = openModal(html`${modalHeader('¿Quieres puntuarlo?')}<div class="comp-body" id="rateBody"></div>`);
  const body = modal.el.querySelector('#rateBody');
  let message = '';

  const draw = () => {
    mount(body, html`
      <div><strong>${game.name}</strong></div>
      <form class="comp-score" id="rateForm" novalidate>
        <label>Tu nota (${SCORE_MIN}-${SCORE_MAX})
          <input class="adm-input" type="number" name="score" value="${current ?? ''}" min="${SCORE_MIN}" max="${SCORE_MAX}" step="1" placeholder="${SCORE_MIN}-${SCORE_MAX}" title="${SCORE_HINT}" />
        </label>
      </form>
      <div class="sess-error" role="alert">${message}</div>
      <div class="sess-actions">
        <span class="sess-spacer"></span>
        <button type="button" class="sess-btn" data-close>Ahora no</button>
        <button type="submit" class="sess-btn primary" form="rateForm">Guardar nota</button>
      </div>`);
    body.querySelector('input').focus();
  };

  body.addEventListener('submit', async (e) => {
    e.preventDefault();
    const value = parseScore(e.target.elements.score.value);
    if (value == null || Number.isNaN(value)) {
      message = SCORE_HINT;
      return draw();
    }
    try {
      await saveScore(username, game.id, value);
    } catch (err) {
      message = err.message;
      return draw();
    }
    modal.close();
    toast(`Nota guardada: ${value}`);
    await onSaved?.();
  });

  draw();
}
