// The recap of the month that ended, offered in the first days of a month: a bar at the top when the app opens (once: opening it
// or closing it is seeing it) and a card in the profile for as long as the days last. Not everybody has push on, and the
// notice is the only way those players ever hear of it.
import { api } from '../lib/api.js';
import { html, mount } from '../lib/html.js';
import { lastMonth, periodLabel, recapHref } from '../lib/recap.js';
import { hasSeen, markSeen, windowPeriods } from '../lib/recap-window.js';
import { storyHref } from '../lib/story.js';

const banner = () => document.querySelector('.recap-invite');

/** Opening the story of a period counts as seeing the notice: it is gone and does not come back. */
export function dismissRecapInvite(period) {
  markSeen(period);
  banner()?.remove();
}

const busy = () => banner() || location.hash.startsWith('#/story');

/** Show the bar for the first period on offer that this device has not shown yet and the player played in (in January there
 * are two, the season and December: the second one comes the next time the app opens). */
export async function inviteToRecap(user, now = new Date()) {
  if (busy()) return;
  for (const period of windowPeriods(now)) {
    if (hasSeen(period)) continue;
    const data = await api(`/statistics/recap/${period}?username=${encodeURIComponent(user.username)}`);
    // the answer takes a moment: the player may have opened the story meanwhile
    if (busy()) return;
    if (data?.player?.seconds && !hasSeen(period)) return showBar(period);
  }
}

function showBar(period) {
  const bar = document.createElement('div');
  bar.className = 'recap-invite';
  bar.setAttribute('role', 'status');
  document.body.appendChild(bar);
  mount(bar, html`
    <div class="recap-invite-text"><strong>🎬 Ya está disponible tu resumen de ${periodLabel(period)}</strong><span>Míralo en historias y compártelo con quien quieras.</span></div>
    <div class="recap-invite-actions">
      <a class="pf-btn primary" href="${storyHref(period)}" data-act="open">Verlo</a>
      <button class="recap-invite-close" type="button" data-act="close" aria-label="Cerrar">×</button>
    </div>`);
  bar.addEventListener('click', (event) => {
    if (event.target.closest('[data-act]')) dismissRecapInvite(period); // the link goes on to the story by itself
  });
}

/** The cards of the profile while the days last, one per period on offer, or nothing. Always there in those days: it is not the notice.
 * With the recaps open (`always`) the card is there every day, for the month that ended once the days are over. */
export function recapCard(now = new Date(), always = false) {
  const periods = windowPeriods(now);
  return html`${(always && !periods.length ? [lastMonth(now)] : periods).map(card)}`;
}

function card(period) {
  return html`
    <div class="pf-card recap-card" data-period="${period}">
      <div class="pf-row">
        <div class="pf-row-main"><strong>🎬 Tu resumen de ${periodLabel(period)} ya está disponible</strong><div class="pf-sub">Tu resumen en historias: juegos, días, géneros y más.</div></div>
        <div class="pf-game-actions">
          <a class="pf-btn primary" href="${storyHref(period)}">Ver historia</a>
          <a class="pf-btn" href="${recapHref(period)}">Ver datos</a>
        </div>
      </div>
    </div>`;
}
