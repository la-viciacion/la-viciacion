// "Playing now": a chip in the navbar (up to three avatars with a green aura, only when somebody else is
// playing) that opens a sheet with who plays what. Your own avatar gets the aura while your timer runs.
import { formatDuration, formatPlayers } from '../lib/format.js';
import { html, mount } from '../lib/html.js';
import { gameHref } from '../lib/links.js';
import { platformName } from '../lib/platforms.js';
import { current, groupByGame, refresh, subscribe, summarize } from '../lib/presence.js';
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

// Two or more players on the same game: one card with all of them ("Bea, Cai y tú estáis jugando a Hades"). It only
// says they play the same game, not that they play together.
function sharedRow(group, myId) {
  const names = group.players.map((p) => (p.user_id === myId ? 'tú' : p.name));
  const mine = group.players.some((p) => p.user_id === myId);
  const latest = group.players.reduce((a, b) => (new Date(a.start_time) > new Date(b.start_time) ? a : b));
  return html`
    <li class="pl-row shared">
      <span class="pl-stack">${group.players.map((p) => playerAvatar(p, 'live'))}</span>
      <div class="pl-info">
        <div class="pl-name">${formatPlayers(names)} ${mine ? 'estáis' : 'están'} jugando a <a href="${gameHref(group.game_id)}">${group.game_name}</a></div>
        <div class="pl-since">${since(latest)}</div>
      </div>
    </li>`;
}

/** The rows of the sheet: players on a shared game first, then the others one by one, then the stale ones. You only
 * appear when you share your game with someone. */
function rowsOf({ fresh, stale, mine }, myId) {
  const groups = groupByGame(mine ? [...fresh, mine] : fresh);
  const shared = groups.filter((g) => g.shared);
  const alone = groups.filter((g) => !g.shared).flatMap((g) => g.players);
  return [...shared.map((g) => sharedRow(g, myId)), ...alone.map(row), ...stale.map(row)];
}

function openSheet(myId) {
  let unsubscribe = () => {};
  const modal = openModal(html`${modalHeader('Jugando ahora')}<ul class="pl-list" id="playingList"></ul>`, { sheet: true, onClose: () => unsubscribe() });
  const list = modal.el.querySelector('#playingList');
  list.addEventListener('click', (e) => { if (e.target.closest('a')) modal.close(); }); // the page changes under the sheet
  const draw = (players) => {
    const rows = rowsOf(summarize(players, myId), myId);
    mount(list, rows.length ? html`${rows}` : html`<li class="pl-empty">Ahora mismo no hay nadie jugando.</li>`);
    hydratePhotos(list);
  };
  unsubscribe = subscribe(draw);
  draw(current());
  refresh();
}

export const openPlayingSheet = openSheet;

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
