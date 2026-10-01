// "Recomendados": a weighted random pick of the games other players have and this user has never had.
// The API decides what is recommended; this only shows it, and asks again for other ones.
import { api } from '../../lib/api.js';
import { formatDuration, formatPlayers } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';

const MAX_GENRES = 3;

const thumb = (g) => (g.image_url
  ? html`<img src="${g.image_url}" alt="" class="pf-thumb" loading="lazy" />`
  : html`<div class="pf-thumb pf-thumb-placeholder" aria-hidden="true">🎮</div>`);

function detail(g) {
  const completed = g.completed_by
    ? ` · ${g.completed_by === 1 ? 'Lo ha completado 1' : `Lo han completado ${g.completed_by}`}`
    : '';
  const played = g.played_seconds ? ` · ${formatDuration(g.played_seconds)} jugadas entre todos` : '';
  return `Lo ${g.players.length === 1 ? 'tiene' : 'tienen'} ${formatPlayers(g.players)}${completed}${played}`;
}

const row = (g) => html`
  <div class="pf-game">
    ${thumb(g)}
    <div class="pf-row-main">
      <div class="pf-game-title">
        <strong>${g.game_name}</strong>
        ${g.genres.slice(0, MAX_GENRES).map((genre) => html`<span class="pf-tag muted">${genre}</span>`)}
      </div>
      <div class="pf-sub">${detail(g)}</div>
    </div>
  </div>`;

export async function initRecommendations(container, { username }) {
  async function load() {
    try {
      const items = await api(`/users/${encodeURIComponent(username)}/recommendations`);
      if (!items) return;
      mount(container, html`
        <div class="pf-card">
          ${items.length
    ? items.map(row)
    : html`<div class="pf-empty">No hay nada que recomendarte: ya has probado todo lo que tienen los demás.</div>`}
          ${items.length ? html`<div><button class="pf-btn" data-more>🎲 Otras recomendaciones</button></div>` : ''}
        </div>`);
    } catch (err) {
      mount(container, html`<div class="pf-empty">Error cargando las recomendaciones: ${err.message}</div>`);
    }
  }

  container.addEventListener('click', (e) => {
    const more = e.target.closest('[data-more]');
    if (!more) return;
    more.disabled = true;
    load();
  });
  await load();
}
