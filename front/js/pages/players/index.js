// Players page (#/players): the group, each player with their figures and what they are playing now, leading to
// their public page. GET /group/players (derived, nothing stored).
import { api } from '../../lib/api.js';
import { formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { hydratePhotos, playerAvatar } from '../../ui/avatar.js';

export const active = null; // it belongs to no item of the top bar

const card = (p) => html`
  <a class="pl-card" href="#/player/${p.user_id}">
    ${playerAvatar(p, p.playing ? 'live' : '')}
    <div class="pl-card-main">
      <div class="pl-card-name">${p.name}${p.is_me ? ' (tú)' : ''}</div>
      <div class="pf-sub">${p.playing
        ? html`<span class="pf-tag live">Jugando</span> ${p.playing.game_name}`
        : (p.last_played ? `Última sesión: ${formatRelative(p.last_played)}` : 'Todavía no ha jugado')}</div>
      <div class="pf-sub">${formatDuration(p.played_seconds)} · ${p.games} ${p.games === 1 ? 'juego' : 'juegos'} · ${p.completed} completados · ${p.achievements} ${p.achievements === 1 ? 'logro' : 'logros'}</div>
    </div>
  </a>`;

export async function render({ main }) {
  mount(main, html`
    <div class="section-header"><h2 class="section-title">Jugadores</h2><div class="section-line"></div></div>
    <div id="plList"><div class="loading-spinner">Cargando jugadores...</div></div>`);
  try {
    const list = await api('/group/players');
    if (!list) return;
    mount(main.querySelector('#plList'), list.length
      ? html`<div class="pl-cards">${list.map(card)}</div>`
      : html`<div class="pf-empty">Todavía no hay jugadores.</div>`);
    hydratePhotos(main);
  } catch (err) {
    mount(main.querySelector('#plList'), html`<div class="pf-empty">Error cargando los jugadores: ${err.message}</div>`);
  }
}
