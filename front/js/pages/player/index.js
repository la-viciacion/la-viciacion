// Player page (#/player/<id>): what is public of a player: figures of a season or of all of them, most played
// games with their ratings, latest achievements and what they are playing now. GET /group/players/{id}?season=.
// It reuses the pieces of the profile summary; there is no library, email or settings here.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import * as seasons from '../../lib/seasons.js';
import { hydratePhotos, playerAvatar } from '../../ui/avatar.js';
import { achievementsView, sectionTitle, seasonName, seasonPills, seasonSuffix, statsView, topView } from '../../ui/profile-summary.js';

export const active = null; // it belongs to no item of the top bar

let main;
let playerId;
let shown = null; // the season asked for: a year, seasons.ALL, or null = the running one

const back = () => (history.length > 1 ? history.back() : (location.hash = '#/players'));

function draw(d) {
  const header = { user_id: d.user.id, name: d.user.name };
  mount(main, html`
    <button class="pf-btn gm-back" type="button" id="plBack">← Volver</button>
    <div class="pf-head">
      ${playerAvatar(header, d.playing ? 'live' : '')}
      <div class="pf-head-text">
        <h1 class="pf-title">${d.user.name}${d.is_me ? ' (tú)' : ''}</h1>
        <div class="pf-sub">@${d.user.username}${d.is_active === false ? html` <span class="pf-tag muted">Inactivo</span>` : ''}</div>
        ${d.playing ? html`<div class="pf-sub"><span class="pf-tag live">Jugando ahora</span> <a class="game-link" href="${gameHref(d.playing.game_id)}">${d.playing.game_name}</a></div>` : ''}
      </div>
    </div>

    <div class="pf-season" id="plSeasons" role="group" aria-label="Temporada">${seasonPills(d)}</div>
    <section class="pf-stats" aria-label="Estadísticas: ${seasonName(d)}">${statsView(d)}</section>

    <div class="pf-cols">
      <div>
        ${sectionTitle(`Más jugados ${seasonSuffix(d)}`)}
        <div class="pf-card">${topView(d)}</div>
      </div>
      <div>
        ${sectionTitle(`Logros ${seasonSuffix(d)}`)}
        <div class="pf-card">${achievementsView(d, d.is_me)}</div>
      </div>
    </div>`);
  hydratePhotos(main);
  main.querySelector('#plBack').addEventListener('click', back);
  main.querySelector('#plSeasons').addEventListener('click', (e) => {
    const pill = e.target.closest('[data-season]');
    if (!pill || pill.getAttribute('aria-pressed') === 'true') return;
    shown = pill.dataset.season === seasons.ALL ? seasons.ALL : Number(pill.dataset.season);
    load();
  });
}

async function load() {
  try {
    const data = await api(`/group/players/${encodeURIComponent(playerId)}${shown == null ? '' : `?season=${shown}`}`);
    if (data) draw(data);
  } catch (err) {
    mount(main, html`<button class="pf-btn gm-back" type="button" id="plBack">← Volver</button><div class="pf-empty">${err.status === 404 ? 'Este jugador no existe.' : err.message}</div>`);
    main.querySelector('#plBack').addEventListener('click', back);
  }
}

export async function render(ctx) {
  main = ctx.main;
  playerId = decodeURIComponent(location.hash.split('/')[2] || '');
  shown = null;
  await load();
}
