// Players page (#/players): the group, each player with their figures and what they are playing now, leading to
// their public page. GET /group/players (derived, nothing stored).
import { api } from '../../lib/api.js';
import { formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { hydratePhotos, playerAvatar } from '../../ui/avatar.js';

export const active = null; // it belongs to no item of the top bar

const figure = (value, label) => html`<div class="pl-fig"><div class="pl-fig-label">${label}</div><div class="pl-fig-value">${value}</div></div>`;

const card = (p) => html`
  <a class="pl-card${p.playing ? ' live' : ''}${p.is_active ? '' : ' inactive'}" href="#/player/${p.user_id}">
    <div class="pl-card-head">
      ${playerAvatar(p, p.playing ? 'live' : '')}
      <div class="pl-card-main">
        <div class="pl-card-name">${p.name}${p.is_me ? ' (tú)' : ''}${p.is_active ? '' : html` <span class="pf-tag muted">Inactivo</span>`}</div>
        <div class="pf-sub">${p.playing
          ? html`<span class="pf-tag live">Jugando</span> ${p.playing.game_name}`
          : (p.last_played ? `Última sesión: ${formatRelative(p.last_played)}` : 'Todavía no ha jugado')}</div>
      </div>
    </div>
    <div class="pl-figs">
      ${figure(`${Math.floor(p.played_seconds / 3600)} h`, 'Tiempo')}
      ${figure(p.games, p.games === 1 ? 'Juego' : 'Juegos')}
      ${figure(p.completed, p.completed === 1 ? 'Completado' : 'Completados')}
    </div>
  </a>`;

const filters = [['all', 'Todos'], ['active', 'Activos']];

const cards = (list, filter) => {
  const shown = filter === 'active' ? list.filter((p) => p.is_active) : list;
  return shown.length
    ? html`<div class="pl-cards">${shown.map(card)}</div>`
    : html`<div class="pf-empty">Todavía no hay jugadores.</div>`;
};

export async function render({ main }) {
  mount(main, html`
    <h1 class="pf-title pg-title">Jugadores</h1>
    <div id="plList"><div class="loading-spinner">Cargando jugadores...</div></div>`);
  try {
    const list = await api('/group/players');
    if (!list) return;
    const draw = (filter) => {
      mount(main.querySelector('#plList'), html`
        <div class="pf-season" role="group" aria-label="Filtrar jugadores">${filters.map(([key, label]) => html`
          <button type="button" class="pf-season-badge" data-filter="${key}" aria-pressed="${String(key === filter)}">${label}</button>`)}
        </div>
        ${cards(list, filter)}`);
      hydratePhotos(main);
    };
    draw('all');
    main.querySelector('#plList').addEventListener('click', (e) => {
      const pill = e.target.closest('[data-filter]');
      if (pill) draw(pill.dataset.filter);
    });
  } catch (err) {
    mount(main.querySelector('#plList'), html`<div class="pf-empty">Error cargando los jugadores: ${err.message}</div>`);
  }
}
