// "Mis retos" card of the Home: the challenges that are running for the player and how they stand, so they are seen
// without opening #/challenges. GET /challenges?status=active (progress is derived there, never stored).
import { api } from '../../lib/api.js';
import { digest, digestLine } from '../../lib/challenges.js';
import { html, mount } from '../../lib/html.js';

// Only the ones that need attention most (the digest sorts them): the Home is for the timers, #/challenges has the rest.
const SHOWN = 2;

/** Fill `el` with the running challenges of the player; nothing at all when there are none (or they fail to load:
 * this card is a courtesy, the Home does not need it). */
export async function showMyChallenges(el, userId) {
  let list;
  try {
    list = await api('/challenges?status=active');
  } catch {
    return;
  }
  const summary = list ? digest(list, userId) : null;
  if (!summary?.items.length) {
    mount(el, html``);
    return;
  }
  const shown = summary.items.slice(0, SHOWN);
  const hidden = summary.items.length - shown.length;
  mount(el, html`
    <div class="section-header"><h2 class="section-title">Mis retos</h2><div class="section-line"></div></div>
    <a class="pf-card ch-mine" href="#/challenges">
      <span class="pf-sub">${digestLine(summary)}</span>
      ${shown.map(({ challenge, standing }) => html`
        <div class="ch-mine-item ${standing.tone}" data-challenge="${challenge.id}">
          <strong>${challenge.title}</strong>
          <span>${standing.text}</span>
        </div>`)}
      ${hidden ? html`<span class="pf-sub">y ${hidden} más →</span>` : ''}
    </a>`);
}
