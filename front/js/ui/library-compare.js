// "Tu biblioteca y la de <jugador>" of a player's page: the games you both have, the ones only you have and the ones
// only they have. GET /group/players/{id}/compare (derived from the libraries; nothing is stored).
import { api } from '../lib/api.js';
import { formatDuration } from '../lib/format.js';
import { html, mount } from '../lib/html.js';
import { gameHref } from '../lib/links.js';
import { scoreBadge } from './score-badge.js';

const SHOWN = 8; // games drawn per list until "Mostrar más"

const GROUPS = [
  ['shared', 'Los dos lo tenéis'],
  ['only_mine', 'Solo lo tienes tú'],
  ['only_theirs', 'Solo lo tiene'],
];

/** "3 h · completado · nota" of one side of a game, or nothing when that player does not have it. */
function side(label, entry) {
  if (!entry) return '';
  return html`<span class="lc-side">${label}: ${formatDuration(entry.seconds)}${entry.completed ? ' · completado' : ''} ${scoreBadge(entry.score)}</span>`;
}

function listView(key, title, games, limit, name) {
  if (!games.length) return '';
  const both = key === 'shared';
  return html`
    <details class="lc-list" data-list="${key}" open>
      <summary><strong>${key === 'only_theirs' ? `${title} ${name}` : title}</strong> <span class="pf-sub">${games.length}</span></summary>
      <ul class="lc-games">
        ${games.slice(0, limit).map((g) => html`
          <li><a class="game-link" href="${gameHref(g.game_id)}">${g.game_name}</a>
            <div class="pf-sub">${both ? html`${side('Tú', g.mine)} ${side(name, g.theirs)}` : side('', g.mine || g.theirs)}</div></li>`)}
      </ul>
      ${games.length > limit ? html`<button class="pf-btn" type="button" data-more="${key}">Mostrar más (${games.length - limit})</button>` : ''}
    </details>`;
}

/** Fill `el` with the comparison of your library with the player's; nothing at all if it cannot be loaded. */
export async function showLibraryCompare(el, playerId) {
  let data;
  try {
    data = await api(`/group/players/${encodeURIComponent(playerId)}/compare`);
  } catch {
    return;
  }
  if (!data) return;
  const limits = { shared: SHOWN, only_mine: SHOWN, only_theirs: SHOWN };
  const name = data.player.name;
  const draw = () => mount(el, html`
    <div class="pf-sub lc-counts">
      ${data.counts.shared} en común · ${data.counts.only_mine} solo tuyos · ${data.counts.only_theirs} solo de ${name}
    </div>
    ${GROUPS.map(([key, title]) => listView(key, title, data[key], limits[key], name))}
    ${data.counts.shared + data.counts.only_mine + data.counts.only_theirs ? '' : html`<div class="pf-empty">Ninguno de los dos tiene juegos todavía.</div>`}`);
  el.onclick = (e) => {
    const more = e.target.closest('[data-more]');
    if (!more) return;
    limits[more.dataset.more] += SHOWN * 4;
    draw();
  };
  draw();
}
