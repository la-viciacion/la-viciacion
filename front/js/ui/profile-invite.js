// The nudge to complete the profile: a bar when the app opens ("Ahora no" makes it wait, see lib/profile-completeness.js) and
// a card in the profile that is always there while something is missing. It asks for the photo, the city and the birth date
// and never says what they are for.
import { api, loadAvatarUrl } from '../lib/api.js';
import { html, mount } from '../lib/html.js';
import { fillHref, markComplete, markShown, mayAsk, missingSteps, missingText, needsSettings, percent, snooze } from '../lib/profile-completeness.js';

const banner = () => document.querySelector('.profile-invite');

// "Completar" is not an answer that spends a reminder, but the bar must not come back on the next page of the same visit
let followed = false;

// one bar at a time (the others of the app come first) and none in the profile itself, where the card is
const busy = () => followed || banner() || document.querySelector('.push-invite, .recap-invite') || location.hash.startsWith('#/profile');

/** What the profile lacks, from the photo and the settings the API has. */
export async function loadMissing(username) {
  const [avatar, settings] = await Promise.all([loadAvatarUrl(username), api(`/users/${encodeURIComponent(username)}/settings`)]);
  return missingSteps({ hasAvatar: Boolean(avatar), settings });
}

export async function inviteToProfile(user, now = new Date()) {
  if (busy() || !mayAsk(user.username, now)) return;
  const missing = await loadMissing(user.username);
  if (!missing.length) return markComplete(user.username);
  // the answer takes a moment: another bar may have come up meanwhile
  if (busy()) return;

  const bar = document.createElement('div');
  bar.className = 'profile-invite';
  bar.setAttribute('role', 'status');
  document.body.appendChild(bar);
  markShown(user.username, now);
  mount(bar, html`
    <div class="profile-invite-text"><strong>Tu perfil está al ${percent(missing)} %</strong><span>${missingText(missing)}.</span></div>
    <div class="profile-invite-actions">
      <a class="pf-btn primary" href="${fillHref(missing)}" data-act="fill">Completar</a>
      <button class="pf-btn" type="button" data-act="later">Ahora no</button>
    </div>`);
  bar.addEventListener('click', (event) => {
    const act = event.target.closest('[data-act]')?.dataset.act;
    if (!act) return;
    if (act === 'later') snooze(user.username, now);
    else followed = true;
    bar.remove(); // the link goes on to the profile by itself
  });
}

/** The card of the profile, or nothing when it is complete. Its button (`data-go`) opens Ajustes, where the city and the birth date are. */
export function profileCard(missing) {
  if (!missing.length) return html``;
  return html`
    <div class="pf-card profile-card">
      <div class="pf-row">
        <div class="pf-row-main">
          <strong>Tu perfil está al ${percent(missing)} %</strong>
          <div class="pf-sub">${missingText(missing)}.</div>
        </div>
        ${needsSettings(missing) ? html`<button class="pf-btn" type="button" data-go="ajustes">Completar</button>` : ''}
      </div>
      <div class="pf-bar" role="progressbar" aria-label="Perfil completado" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent(missing)}"><div style="width:${percent(missing)}%"></div></div>
    </div>`;
}
