// Wishlist page (#/wishlist): the games you want to play, with the ones that are not out yet first (the nearest
// release on top). GET /group/wishlist; only the wish is stored, a game leaves the list when you start playing it.
// A game is added from RAWG with the same search as the Juegos page, so an announced game is there too.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { releaseLine, wantedBy } from '../../lib/wishlist.js';
import { iconPlus } from '../../ui/icons.js';
import { toast } from '../../ui/toast.js';
import { openAddGame } from '../home/game-picker.js';

export const active = null; // it belongs to no item of the top bar

let main;
let user;

const card = (g) => html`
  <div class="gc-card wl-card">
    <a class="wl-link" href="${gameHref(g.id)}">
      ${g.image_url
        ? html`<img src="${g.image_url}" alt="" class="gc-cover" loading="lazy" />`
        : html`<div class="gc-cover gc-cover-placeholder" aria-hidden="true">🎮</div>`}
      <div class="gc-body">
        <div class="gc-name">${g.name}</div>
        <div class="gc-tags">${g.genres.slice(0, 2).map((genre) => html`<span class="pf-tag muted">${genre}</span>`)}</div>
        <div class="gc-meta"><span>${releaseLine(g)}</span></div>
        ${g.wanted_by.length ? html`<div class="pf-sub">${wantedBy(g.wanted_by)}</div>` : ''}
      </div>
    </a>
    <button class="wl-remove" type="button" data-remove="${g.id}" aria-label="Quitar ${g.name} de la lista" title="Quitar de la lista">×</button>
  </div>`;

const section = (title, games, empty) => html`
  <div class="section-header"><h2 class="section-title">${title}</h2><div class="section-line"></div></div>
  ${games.length ? html`<div class="gc-grid">${games.map(card)}</div>` : html`<div class="pf-empty wl-empty">${empty}</div>`}`;

function draw({ upcoming, wanted }) {
  mount(main.querySelector('#wlLists'), upcoming.length + wanted.length
    ? html`
      ${section('Próximos lanzamientos', upcoming, 'Ningún juego pendiente de salir en tu lista.')}
      ${section('Quiero jugar', wanted, 'Ningún juego ya lanzado en tu lista.')}`
    : html`<div class="pf-empty">Tu lista está vacía. Añade los juegos a los que quieres jugar, también los que todavía no han salido.</div>`);
}

async function load() {
  try {
    const lists = await api('/group/wishlist');
    if (lists) draw(lists);
  } catch (err) {
    mount(main.querySelector('#wlLists'), html`<div class="pf-empty">Error cargando tu lista: ${err.message}</div>`);
  }
}

async function wish(gameId) {
  try {
    await api(`/users/${encodeURIComponent(user.username)}/wishlist/${encodeURIComponent(gameId)}`, { method: 'PUT' });
    toast('Añadido a tu lista');
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

async function unwish(gameId) {
  try {
    await api(`/users/${encodeURIComponent(user.username)}/wishlist/${encodeURIComponent(gameId)}`, { method: 'DELETE' });
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  mount(main, html`
    <div class="wl-head">
      <h1 class="pf-title">Lista de deseados</h1>
      <button class="pf-btn primary" type="button" id="wlAdd">${iconPlus()} Añadir juego</button>
    </div>
    <div id="wlLists"><div class="loading-spinner">Cargando tu lista...</div></div>`);
  main.querySelector('#wlAdd').addEventListener('click', () => openAddGame((id) => wish(id)));
  main.querySelector('#wlLists').addEventListener('click', (e) => {
    const button = e.target.closest('[data-remove]');
    if (button) unwish(button.dataset.remove);
  });
  await load();
}
