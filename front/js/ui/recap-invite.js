// The recap of the month that ended, offered in the first days of a month: a bar at the top when the app opens (once: opening it
// or closing it is seeing it) and a card in the profile for as long as the days last. Not everybody has push on, and the
// notice is the only way those players ever hear of it.
import { api } from '../lib/api.js';
import { html, mount } from '../lib/html.js';
import { periodLabel, recapHref } from '../lib/recap.js';
import { hasSeen, markSeen, windowPeriod } from '../lib/recap-window.js';
import { storyHref } from '../lib/story.js';

const banner = () => document.querySelector('.recap-invite');

/** Opening the story of a period counts as seeing the notice: it is gone and does not come back. */
export function dismissRecapInvite(period) {
  markSeen(period);
  banner()?.remove();
}

/** Show the bar if today is in the first days of a month, this device has not shown it yet and the player played. */
export async function inviteToRecap(user, now = new Date()) {
  const period = windowPeriod(now);
  if (!period || hasSeen(period) || banner() || location.hash.startsWith('#/story')) return;
  const data = await api(`/statistics/recap/${period}?username=${encodeURIComponent(user.username)}`);
  // the answer takes a moment: the player may have opened the story meanwhile
  if (!data?.player?.seconds || hasSeen(period) || banner() || location.hash.startsWith('#/story')) return;

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

/** The card of the profile while the days last, or nothing. Always there in those days: it is not the notice. */
export function recapCard(now = new Date()) {
  const period = windowPeriod(now);
  if (!period) return '';
  return html`
    <div class="pf-card recap-card" id="pfRecap">
      <div class="pf-row">
        <div class="pf-row-main"><strong>🎬 Tu resumen de ${periodLabel(period)} ya está disponible</strong><div class="pf-sub">Tu mes en historias: juegos, días, géneros y más.</div></div>
        <div class="pf-game-actions">
          <a class="pf-btn primary" href="${storyHref(period)}">Ver historia</a>
          <a class="pf-btn" href="${recapHref(period)}">Ver datos</a>
        </div>
      </div>
    </div>`;
}
