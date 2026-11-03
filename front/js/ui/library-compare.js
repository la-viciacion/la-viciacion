// The games you both have, in a grid inside the card of "En común con <jugador>". GET /group/players/{id}/compare
// (derived from the libraries; nothing is stored). The ones only one of you has say nothing, so they are not drawn.
import { api } from '../lib/api.js';
import { formatDuration } from '../lib/format.js';
import { html, mount } from '../lib/html.js';
import { gameHref } from '../lib/links.js';
import { scoreBadge } from './score-badge.js';

const SHOWN = 12; // games drawn until "Mostrar más"

/** One line of a game: who, the hours (and whether it was completed) and the rating, each in its own column. */
const side = (label, entry) => html`<div class="lc-side"><span class="lc-who">${label}</span><span class="lc-time">${formatDuration(entry.seconds)}${entry.completed ? html` <span class="lc-done">· completado</span>` : ''}</span>${scoreBadge(entry.score)}</div>`;

/** Fill `el` with the games you both have; nothing at all if it cannot be loaded. */
export async function showLibraryCompare(el, playerId) {
  let data;
  try {
    data = await api(`/group/players/${encodeURIComponent(playerId)}/compare`);
  } catch {
    return;
  }
  if (!data) return;
  let limit = SHOWN;
  const name = data.player.name;
  const games = data.shared;
  const draw = () => mount(el, games.length ? html`
    <ul class="lc-games" data-list="shared">
      ${games.slice(0, limit).map((g) => html`
        <li><a class="game-link lc-name" href="${gameHref(g.game_id)}">${g.game_name}</a>
          ${side('Tú', g.mine)}${side(name, g.theirs)}</li>`)}
    </ul>
    ${games.length > limit ? html`<button class="pf-btn" type="button" data-more>Mostrar más (${games.length - limit})</button>` : ''}`
    : html`<div class="pf-empty">Todavía no tenéis ningún juego en común.</div>`);
  el.onclick = (e) => {
    if (!e.target.closest('[data-more]')) return;
    limit += SHOWN * 4;
    draw();
  };
  draw();
}
