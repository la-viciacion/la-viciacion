// Global search: a panel to reach a page, a player or a game from anywhere. Opened by the magnifier of the top bar,
// the tab of the bottom bar of a phone, or "/" and Ctrl+K. The pages and the players are matched in the browser
// (lib/search.js), the games are asked to the API (GET /games/catalog?q=, derived, nothing stored).
import { api } from '../lib/api.js';
import { html, mount } from '../lib/html.js';
import { gameHref } from '../lib/links.js';
import { menuPages } from '../lib/menu.js';
import { matchPages, matchPlayers } from '../lib/search.js';
import { hydratePhotos, playerAvatar } from './avatar.js';
import * as icons from './icons.js';

const DELAY = 250;
const GAMES = 8;

let open = null; // the close function of the panel that is on screen
let user = null;
let shortcut = false;
let players = null; // the group, asked the first time somebody types and kept while the app is open

const pageRow = (p) => html`<a class="search-item" href="${p.href}"><span class="search-ico">${icons[p.icon]()}</span><span class="search-name">${p.label}</span></a>`;

const playerRow = (p) => html`
  <a class="search-item" href="#/player/${p.user_id}">${playerAvatar(p)}<span class="search-name">${p.name}</span>${p.playing ? html`<span class="pf-tag live">Jugando</span>` : ''}</a>`;

const gameRow = (g) => html`
  <a class="search-item" href="${gameHref(g.id)}">
    ${g.image_url ? html`<img class="search-cover" src="${g.image_url}" alt="" loading="lazy" />` : html`<span class="search-cover search-cover-empty" aria-hidden="true">🎮</span>`}
    <span class="search-name">${g.name}</span>${g.have ? html`<span class="pf-tag done">En tu biblioteca</span>` : ''}
  </a>`;

const group = (title, rows) => (rows.length ? html`<div class="search-group">${title}</div>${rows}` : '');

/** What the panel shows for `query`: the matching pages, players and games; the pages to go to when it is empty. */
export function resultsView({ query, pages, found, games, loading }) {
  if (!query.trim()) return html`${group('Ir a', pages.map(pageRow))}`;
  const rows = [group('Páginas', found.pages.map(pageRow)), group('Jugadores', found.players.map(playerRow)), group('Juegos', games.map(gameRow))];
  if (found.pages.length || found.players.length || games.length) return html`${rows}`;
  return html`<div class="search-empty">${loading ? 'Buscando...' : 'No hay nada que coincida.'}</div>`;
}

function openSearch() {
  if (open) return open();
  const pages = menuPages(user);
  const overlay = document.createElement('div');
  overlay.className = 'search-overlay';
  mount(overlay, html`
    <div class="search-panel" role="dialog" aria-modal="true" aria-label="Buscar">
      <div class="search-bar">
        ${icons.iconSearch()}
        <input id="searchInput" type="search" placeholder="Buscar juegos, jugadores o páginas" autocomplete="off" enterkeyhint="go" aria-label="Buscar" />
        <button class="menu-close" type="button" data-close aria-label="Cerrar la búsqueda">${icons.iconClose()}</button>
      </div>
      <div class="search-results" id="searchResults" aria-live="polite"></div>
    </div>`);
  const input = overlay.querySelector('#searchInput');
  const box = overlay.querySelector('#searchResults');
  let timer = null;
  let latest = 0; // an answer to an older query must not replace a newer one

  const draw = (state) => {
    mount(box, resultsView({ pages, ...state }));
    hydratePhotos(box);
  };
  const showPages = () => draw({ query: '', found: { pages: [], players: [] }, games: [] });
  showPages();

  async function search() {
    const query = input.value.trim();
    const mine = ++latest;
    if (!query) return showPages();
    const found = { pages: matchPages(query, pages), players: [] };
    draw({ query, found, games: [], loading: true });
    const [list, page] = await Promise.all([
      (players ??= api('/group/players').catch(() => { players = null; return []; })),
      api(`/games/catalog?limit=${GAMES}&sort=played&q=${encodeURIComponent(query)}`).catch(() => null),
    ]);
    if (mine !== latest) return;
    found.players = matchPlayers(query, list ?? []);
    draw({ query, found, games: page?.items ?? [] });
  }

  function close() {
    if (open !== close) return;
    open = null;
    clearTimeout(timer);
    latest++;
    document.removeEventListener('keydown', onKey);
    overlay.remove();
  }
  function onKey(e) {
    if (e.key === 'Escape') return close();
    if (e.key === 'Enter' && document.activeElement === input) box.querySelector('a.search-item')?.click();
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const links = [...box.querySelectorAll('a.search-item')];
    const at = links.indexOf(document.activeElement);
    const next = e.key === 'ArrowDown' ? at + 1 : at - 1;
    e.preventDefault();
    if (next < 0) input.focus();
    else links[Math.min(next, links.length - 1)]?.focus();
  }

  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, DELAY); });
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay || e.target.closest('[data-close]') || e.target.closest('a.search-item')) close();
  });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(overlay);
  input.focus();
  open = close;
  return close;
}

const typing = (el) => el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));

/** Wires every control marked `data-search` (the magnifier, the tab of the bottom bar) and the shortcuts "/" and Ctrl+K. */
export function mountSearch(root, currentUser) {
  user = currentUser;
  root.querySelectorAll('[data-search]').forEach((el) => el.addEventListener('click', openSearch));
  if (shortcut) return;
  shortcut = true;
  document.addEventListener('keydown', (e) => {
    const slash = e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !typing(document.activeElement);
    const ctrlK = e.key.toLowerCase() === 'k' && (e.ctrlKey || e.metaKey);
    if (!open && user && (slash || ctrlK)) { e.preventDefault(); openSearch(); }
  });
}

/** Closes the search if it is open (a page is leaving, or the session ends). */
export const closeSearch = () => open?.();
