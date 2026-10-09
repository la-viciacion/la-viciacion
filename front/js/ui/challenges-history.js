// The finished challenges of a player, for their profile and for their public page. GET /challenges/player/{id}:
// derived from the sessions, so a result follows the sessions if they are corrected.
import { api } from '../lib/api.js';
import { resultLine } from '../lib/challenges.js';
import { formatDate } from '../lib/format.js';
import { html, mount } from '../lib/html.js';

/** Fill `el` with the history of the player; `isMe` only changes the wording of the empty state. */
export async function showChallengesHistory(el, playerId, isMe = false) {
  let list;
  try {
    list = await api(`/challenges/player/${encodeURIComponent(playerId)}`);
  } catch (err) {
    mount(el, html`<div class="pf-empty">No se pudieron cargar los retos: ${err.message}</div>`);
    return;
  }
  if (!list) return;
  mount(el, list.length
    ? html`<div class="ch-history">${list.map((c) => html`
      <div class="ch-history-item">
        <span><strong>${c.title}</strong> <span class="pf-sub">${formatDate(c.ends_on)}</span></span>
        <span class="pf-tag${c.done ? '' : ' muted'}">${resultLine(c)}</span>
      </div>`)}</div>`
    : html`<div class="pf-empty">${isMe ? 'Todavía no has terminado ningún reto.' : 'Todavía no ha terminado ningún reto.'}</div>`);
}
