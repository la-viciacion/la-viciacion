// Player page (#/player/<id>): what is public of a player: figures of a season or of all of them, most played
// games with their ratings, latest achievements and what they are playing now. GET /group/players/{id}?season=.
// It reuses the pieces of the profile summary; there is no library, email or settings here.
import { api } from '../../lib/api.js';
import { GAME_IDS } from '../../lib/game-ids.js';
import { createFolds, toggleFold } from '../../lib/fold.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import * as seasons from '../../lib/seasons.js';
import { toast } from '../../ui/toast.js';
import { hydratePhotos, playerAvatar } from '../../ui/avatar.js';
import { showChallengesHistory } from '../../ui/challenges-history.js';
import { showLibraryCompare } from '../../ui/library-compare.js';
import { iconChevron } from '../../ui/icons.js';
import { achievementsView, sectionTitle, seasonName, seasonPills, seasonSuffix, statsView, titleView, topView } from '../../ui/profile-summary.js';

export const active = null; // it belongs to no item of the top bar

let main;
let playerId;
const folds = createFolds('player-folds'); // the sections the viewer has folded (remembered in this browser)
let shown = null; // the season asked for: a year, seasons.ALL, or null = the running one

/** The taste in common, over every season, as the head of the card of the games you share; nothing on your own page. */
export function affinityView(a) {
  if (!a) return '';
  const shared = a.shared_games === 1 ? '1 juego en común' : `${a.shared_games} juegos en común`;
  return html`
    <div id="plAffinity" class="pl-affinity">
      ${a.percent == null
        ? html`<div class="pf-sub">Todavía hay pocos datos: ${shared}. Hacen falta al menos 3.</div>`
        : html`<strong class="pf-stat-value">${a.percent} %</strong> <span class="pf-sub">de afinidad · ${shared}${a.shared_rated ? `, ${a.shared_rated} puntuados por los dos` : ''}</span>`}
    </div>`;
}

/** The ids the player filled in, one card per service (nothing at all when they filled none); a click copies it. */
export function gameIdsView(ids) {
  const filled = GAME_IDS.filter(([column]) => ids?.[column]);
  if (!filled.length) return '';
  return html`
    <ul class="pl-ids" id="plIds" aria-label="IDs en otras plataformas">
      ${filled.map(([column, label]) => html`
        <li><button type="button" class="pl-id" data-copy="${ids[column]}" title="Copiar ${label}" aria-label="${label}: ${ids[column]}. Copiar">
          <span class="pl-id-service">${label}</span>
          <span class="pl-id-value">${ids[column]}</span>
        </button></li>`)}
    </ul>`;
}

/** Copy the id of the card clicked and say so. */
async function copyId(e) {
  const card = e.target.closest('[data-copy]');
  if (!card) return;
  try {
    await navigator.clipboard.writeText(card.dataset.copy);
    toast('Copiado');
  } catch {
    toast('No se ha podido copiar', 'err');
  }
}

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

    ${gameIdsView(d.game_ids)}

    <div class="pf-season" id="plSeasons" role="group" aria-label="Temporada">${seasonPills(d)}</div>
    <section class="pf-stats" aria-label="Estadísticas: ${seasonName(d)}">${statsView(d)}</section>

    <div class="pf-cols pl-block">
      <div>
        ${sectionTitle(`Más jugados ${seasonSuffix(d)}`)}
        <div class="pf-card">${topView(d)}</div>
      </div>
      <div>
        ${sectionTitle(`Últimos logros ${seasonSuffix(d)}`)}
        <div class="pf-card">${achievementsView(d, d.is_me)}</div>
      </div>
    </div>

    ${d.is_me ? '' : html`
      <section class="ach-block pl-block ${folds.has('common') ? 'folded' : ''}">
        <button type="button" class="section-header ach-fold" data-fold="common" aria-expanded="${String(!folds.has('common'))}">
          ${titleView(`En común con ${d.user.name}`)}<span class="ach-chevron" aria-hidden="true">${iconChevron()}</span>
        </button>
        <div class="ach-content pf-card">
          ${affinityView(d.affinity)}
          <div id="plCompare"><div class="pf-sub">Cargando...</div></div>
        </div>
      </section>`}

    <div class="pl-block">
      ${sectionTitle('Retos')}
      <div class="pf-card" id="plChallenges"></div>
    </div>`);
  hydratePhotos(main);
  showChallengesHistory(main.querySelector('#plChallenges'), d.user.id, d.is_me);
  if (!d.is_me) showLibraryCompare(main.querySelector('#plCompare'), d.user.id);
  main.querySelector('#plBack').addEventListener('click', back);
  main.querySelector('#plIds')?.addEventListener('click', copyId);
  main.querySelector('[data-fold]')?.addEventListener('click', (e) => toggleFold(folds, 'common', e.currentTarget.closest('.ach-block'), e.currentTarget));
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
