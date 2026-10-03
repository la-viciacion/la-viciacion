// "Playing now": a chip in the navbar (up to three avatars with a green aura, only when somebody else is
// playing) that opens a sheet with who plays what. Your own avatar gets the aura while your timer runs.
import { formatDuration } from '../lib/format.js';
import { html, mount } from '../lib/html.js';
import { gameHref } from '../lib/links.js';
import { platformName } from '../lib/platforms.js';
import { current, refresh, subscribe, summarize } from '../lib/presence.js';
import { hydratePhotos, playerAvatar } from './avatar.js';
import { modalHeader, openModal } from './modal.js';

const CHIP_AVATARS = 3;

function chip(fresh) {
  const extra = fresh.length - CHIP_AVATARS;
  const label = `${fresh.length} jugando ahora: ${fresh.map((p) => p.name).join(', ')}. Ver quién y a qué`;
  return html`
    <button type="button" class="playing-chip" data-open aria-label="${label}" title="Jugando ahora">
      <span class="pl-stack">${fresh.slice(0, CHIP_AVATARS).map((p) => playerAvatar(p, 'live'))}</span>
      ${extra > 0 ? html`<span class="pl-more">+${extra}</span>` : ''}
    </button>`;
}

const since = (p) => `desde hace ${formatDuration(Math.max(0, (Date.now() - new Date(p.start_time)) / 1000))}`;

function row(p) {
  return html`
    <li class="pl-row ${p.stale ? 'stale' : ''}">
      ${playerAvatar(p, p.stale ? 'dim' : 'live')}
      <div class="pl-info">
        <div class="pl-name">${p.name}</div>
        <div class="pl-game"><a href="${gameHref(p.game_id)}">${p.game_name}</a>${p.platform ? ` · ${platformName(p.platform)}` : ''}</div>
        <div class="pl-since">${since(p)}${p.stale ? ' · ¿Un timer olvidado?' : ''}</div>
      </div>
    </li>`;
}

function openSheet(myId) {
  let unsubscribe = () => {};
  const modal = openModal(html`${modalHeader('Jugando ahora')}<ul class="pl-list" id="playingList"></ul>`, { sheet: true, onClose: () => unsubscribe() });
  const list = modal.el.querySelector('#playingList');
  list.addEventListener('click', (e) => { if (e.target.closest('a')) modal.close(); }); // the page changes under the sheet
  const draw = (players) => {
    const { fresh, stale } = summarize(players, myId);
    mount(list, fresh.length + stale.length
      ? html`${[...fresh, ...stale].map(row)}`
      : html`<li class="pl-empty">Ahora mismo no hay nadie jugando.</li>`);
    hydratePhotos(list);
  };
  unsubscribe = subscribe(draw);
  draw(current());
  refresh();
}

/** Fills `slot` (in the navbar) and keeps it in step with the presence state until the slot leaves the page. */
export function mountPlaying(slot, user) {
  const draw = (players) => {
    if (!slot.isConnected) return unsubscribe();
    const { fresh, meActive } = summarize(players, user.id);
    mount(slot, fresh.length ? chip(fresh) : html``);
    hydratePhotos(slot);
    document.querySelector('.navbar-user')?.classList.toggle('playing', meActive);
  };
  const unsubscribe = subscribe(draw);
  slot.addEventListener('click', (e) => { if (e.target.closest('[data-open]')) openSheet(user.id); });
  draw(current());
  refresh();
}
