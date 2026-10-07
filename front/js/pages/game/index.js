// Game page (#/game/<id>): what the group has done with a game. Who has it, their hours, completions and
// ratings, and your own rating. GET /games/{id}/overview; everything is derived, nothing is stored.
import { api } from '../../lib/api.js';
import { formatDate, formatDuration, formatRelative } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { wantedBy } from '../../lib/wishlist.js';
import { hydratePhotos, playerAvatar } from '../../ui/avatar.js';
import { scoreBadge } from '../../ui/score-badge.js';
import { toast } from '../../ui/toast.js';
import { openRating } from '../home/rating.js';

export const active = null; // it belongs to no item of the navbar

let main;
let user;

const gameId = () => decodeURIComponent(location.hash.split('/')[2] || '');

const back = () => (history.length > 1 ? history.back() : (location.hash = '#'));

const tile = (label, value) => html`<div class="pf-stat"><div class="pf-stat-value">${value}</div><div class="pf-stat-label">${label}</div></div>`;

function playerRow(p) {
  const seasons = p.seasons.length > 1 ? `temporadas ${p.seasons.join(', ')}` : `temporada ${p.seasons[0]}`;
  return html`
    <li class="gm-player ${p.is_me ? 'me' : ''}">
      ${playerAvatar(p, p.playing ? 'live' : '')}
      <div class="gm-player-main">
        <div class="gm-player-name">${p.name}${p.is_me ? ' (tú)' : ''}
          ${p.is_active ? '' : html`<span class="pf-tag muted">Inactivo</span>`}
          ${p.playing ? html`<span class="pf-tag live">Jugando ahora</span>` : ''}
          ${p.completed ? html`<span class="pf-tag done">Completado${p.completions > 1 ? ` ×${p.completions}` : ''}</span>` : ''}
        </div>
        <div class="pf-sub">
          ${formatDuration(p.played_seconds)} · ${p.sessions} ${p.sessions === 1 ? 'sesión' : 'sesiones'} · ${seasons}${p.last_played ? ` · última: ${formatRelative(p.last_played)}` : ''}
        </div>
      </div>
      ${scoreBadge(p.score)}
    </li>`;
}

function draw(data) {
  const { game, summary, players } = data;
  const mine = players.find((p) => p.is_me);
  const details = [game.dev, game.release_date ? formatDate(game.release_date) : null,
    game.avg_time ? `se completa en unas ${formatDuration(game.avg_time)}` : null].filter(Boolean).join(' · ');

  mount(main, html`
    <button class="pf-btn gm-back" type="button" id="gmBack">← Volver</button>
    <div class="gm-head">
      ${game.image_url
        ? html`<img src="${game.image_url}" alt="" class="gm-cover" />`
        : html`<div class="gm-cover gm-cover-placeholder" aria-hidden="true">🎮</div>`}
      <div>
        <h1 class="pf-title">${game.name}</h1>
        <div class="gm-genres">${game.genres.map((genre) => html`<span class="pf-tag muted">${genre}</span>`)}</div>
        ${details ? html`<div class="pf-sub">${details}</div>` : ''}
      </div>
    </div>

    <section class="pf-stats" aria-label="El grupo y este juego">
      ${tile('Jugadores', summary.players)}
      ${tile('Horas del grupo', formatDuration(summary.played_seconds))}
      ${tile('Completados', summary.completed_by)}
      ${tile(summary.score_count ? `Nota media (${summary.score_count})` : 'Nota media', summary.score_count ? scoreBadge(Math.round(summary.score_mean)) : '—')}
    </section>

    ${data.wanted_by.length ? html`<div class="pf-sub gm-wanted">${wantedBy(data.wanted_by)}</div>` : ''}
    ${mine ? '' : html`
      <div class="pf-card gm-mine">
        <div>${data.wished ? 'Está en tu lista de deseados.' : html`<span class="pf-sub">No lo tienes en tu biblioteca.</span>`}</div>
        <button class="pf-btn" type="button" id="gmWish">${data.wished ? 'Quitar de mi lista' : 'Añadir a mi lista'}</button>
      </div>`}
    ${mine ? html`
      <div class="pf-card gm-mine">
        <div>${mine.score == null ? html`<span class="pf-sub">Todavía no lo has puntuado.</span>` : html`Tu nota ${scoreBadge(mine.score)}`}</div>
        <button class="pf-btn" type="button" id="gmRate">${mine.score == null ? 'Puntuar' : 'Cambiar nota'}</button>
      </div>` : ''}

    <div class="section-header"><h2 class="section-title">Quién lo juega</h2><div class="section-line"></div></div>
    ${players.length
      ? html`<ul class="gm-players pf-card">${players.map(playerRow)}</ul>`
      : html`<div class="pf-empty">Nadie del grupo lo tiene todavía.</div>`}`);

  hydratePhotos(main);
  main.querySelector('#gmBack').addEventListener('click', back);
  main.querySelector('#gmWish')?.addEventListener('click', () => toggleWish(game.id, data.wished));
  main.querySelector('#gmRate')?.addEventListener('click', () => openRating({
    username: user.username, game: { id: game.id, name: game.name }, current: mine.score, onSaved: load,
  }));
}

async function toggleWish(id, wished) {
  try {
    const [username, game] = [user.username, id].map(encodeURIComponent);
    if (wished) await api(`/users/${username}/wishlist/${game}`, { method: 'DELETE' });
    else await api(`/users/${username}/wishlist/${game}`, { method: 'PUT' });
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

async function load() {
  try {
    const data = await api(`/games/${encodeURIComponent(gameId())}/overview`);
    if (data) draw(data);
  } catch (err) {
    mount(main, html`<button class="pf-btn gm-back" type="button" id="gmBack">← Volver</button><div class="pf-empty">${err.status === 404 ? 'Este juego no existe.' : err.message}</div>`);
    main.querySelector('#gmBack').addEventListener('click', back);
  }
}

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  await load();
}
