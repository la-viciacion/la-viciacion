// Games page (#/games): the whole catalog, with search, filters and order, as the way into each game's page.
// GET /games/catalog (derived, nothing stored); a game can also be added from RAWG here.
import { api } from '../../lib/api.js';
import { formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { iconPlus } from '../../ui/icons.js';
import { scoreBadge } from '../../ui/score-badge.js';
import { openAddGame } from '../home/game-picker.js';

export const active = null; // it belongs to no item of the top bar

const PAGE = 24;
const SEARCH_DELAY = 300;

export const SORTS = [
  ['activity', 'Actividad reciente'],
  ['played', 'Más jugados'],
  ['rated', 'Mejor valorados'],
  ['players', 'Más jugadores'],
  ['release', 'Fecha de salida'],
  ['name', 'Nombre'],
];

// The toggle filters: [API key, label]
const TOGGLES = [
  ['playing', 'Jugándose ahora'],
  ['with_players', 'Con jugadores'],
  ['completed', 'Completados por mí'],
  ['rated', 'Puntuados por mí'],
];

let main;
let items = [];
let total = 0;
let genres = [];
let timer = null;
let latest = 0; // an answer to an older request must not replace a newer one
const filters = { q: '', genre: '', library: '', sort: 'activity', playing: false, with_players: false, completed: false, rated: false };

/** The query string of the API for some filters (only what is set). */
export function catalogQuery(f, offset = 0) {
  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset), sort: f.sort });
  for (const key of ['q', 'genre', 'library']) if (f[key]) params.set(key, f[key]);
  for (const [key] of TOGGLES) if (f[key]) params.set(key, 'true');
  return params.toString();
}

const card = (g) => html`
  <a class="gc-card" href="${gameHref(g.id)}">
    ${g.image_url
      ? html`<img src="${g.image_url}" alt="" class="gc-cover" loading="lazy" />`
      : html`<div class="gc-cover gc-cover-placeholder" aria-hidden="true">🎮</div>`}
    <div class="gc-body">
      <div class="gc-name">${g.name}</div>
      <div class="gc-tags">
        ${g.playing_now ? html`<span class="pf-tag live">Jugándose</span>` : ''}
        ${g.have ? html`<span class="pf-tag done">En tu biblioteca</span>` : ''}
        ${g.wished ? html`<span class="pf-tag wish">En tu lista</span>` : ''}
        ${g.genres.slice(0, 2).map((genre) => html`<span class="pf-tag muted">${genre}</span>`)}
      </div>
      <div class="gc-meta">
        <span>${g.players === 1 ? '1 jugador' : `${g.players} jugadores`}${g.played_seconds ? ` · ${formatDuration(g.played_seconds)}` : ''}</span>
        ${g.score_mean == null ? '' : html`<span class="gc-score" title="Nota media del grupo (${g.score_count})">${scoreBadge(Math.round(g.score_mean))}</span>`}
      </div>
    </div>
  </a>`;

function drawResults() {
  const remaining = total - items.length;
  mount(main.querySelector('#gcResults'), items.length
    ? html`<div class="gc-grid">${items.map(card)}</div>
        ${remaining > 0 ? html`<button class="pf-btn" type="button" id="gcMore">Mostrar más (${remaining})</button>` : ''}`
    : html`<div class="pf-empty">Ningún juego coincide con estos filtros.</div>`);
  main.querySelector('#gcMore')?.addEventListener('click', loadMore);
  main.querySelector('#gcCount').textContent = total === 1 ? '1 juego' : `${total} juegos`;
}

async function load() {
  const mine = ++latest;
  try {
    const page = await api(`/games/catalog?${catalogQuery(filters)}`);
    if (!page || mine !== latest) return;
    ({ items, total } = page);
    if (!genres.length) {
      genres = page.genres;
      mount(main.querySelector('#gcGenre'), html`<option value="">Todos los géneros</option>${genres.map((g) => html`<option value="${g}">${g}</option>`)}`);
    }
    drawResults();
  } catch (err) {
    mount(main.querySelector('#gcResults'), html`<div class="pf-empty">Error cargando los juegos: ${err.message}</div>`);
  }
}

async function loadMore() {
  const page = await api(`/games/catalog?${catalogQuery(filters, items.length)}`);
  if (!page) return;
  items = items.concat(page.items);
  total = page.total;
  drawResults();
}

function bind() {
  const search = main.querySelector('#gcSearch');
  search.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { filters.q = search.value.trim(); load(); }, SEARCH_DELAY);
  });
  const select = (id, key) => main.querySelector(id).addEventListener('change', (e) => { filters[key] = e.target.value; load(); });
  select('#gcSort', 'sort');
  select('#gcGenre', 'genre');
  select('#gcLibrary', 'library');
  main.querySelector('#gcToggles').addEventListener('click', (e) => {
    const button = e.target.closest('[data-toggle]');
    if (!button) return;
    const key = button.dataset.toggle;
    filters[key] = !filters[key];
    button.setAttribute('aria-pressed', String(filters[key]));
    load();
  });
  // a game added here has nobody yet: go to its page, where it can be rated or played
  main.querySelector('#gcAdd').addEventListener('click', () => openAddGame((id) => { location.hash = gameHref(id); }));
}

export async function render(ctx) {
  main = ctx.main;
  clearTimeout(timer);
  genres = [];
  items = [];
  Object.assign(filters, { q: '', genre: '', library: '', sort: 'activity', playing: false, with_players: false, completed: false, rated: false });

  mount(main, html`
    <h1 class="pf-title pg-title">Juegos</h1>
    <div class="gc-toolbar">
      <input class="adm-input gc-search" id="gcSearch" type="search" placeholder="Buscar un juego…" autocomplete="off" aria-label="Buscar un juego" />
      <button class="pf-btn primary" type="button" id="gcAdd">${iconPlus()} Añadir juego</button>
    </div>
    <div class="gc-toolbar">
      <select class="adm-input" id="gcSort" aria-label="Ordenar por">${SORTS.map(([value, label]) => html`<option value="${value}">${label}</option>`)}</select>
      <select class="adm-input" id="gcGenre" aria-label="Género"><option value="">Todos los géneros</option></select>
      <select class="adm-input" id="gcLibrary" aria-label="Tu biblioteca">
        <option value="">Toda la base de datos</option><option value="have">Los que tengo</option><option value="not">Los que no tengo</option>
      </select>
    </div>
    <div class="gc-toggles" id="gcToggles" role="group" aria-label="Filtros">
      ${TOGGLES.map(([key, label]) => html`<button type="button" class="gc-toggle" data-toggle="${key}" aria-pressed="false">${label}</button>`)}
    </div>
    <div class="pf-sub gc-count" id="gcCount" role="status"></div>
    <div id="gcResults"><div class="loading-spinner">Cargando juegos...</div></div>`);
  bind();
  await load();
}

export function dispose() {
  clearTimeout(timer);
}
