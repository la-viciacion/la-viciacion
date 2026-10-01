// Game picker (own catalogue, or add one from RAWG) shared by two flows:
//   "Nuevo timer": pick a game -> pick a platform -> start the timer
//   "Sesión manual": pick a game -> fill the session form (see sessions.js)
// Each step is a modal; the picker hands the chosen game to `onPick(id, name)`.
import { api, jsonRequest } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { platformList, platformName } from '../../lib/platforms.js';
import { iconPlus } from '../../ui/icons.js';
import { closeAllModals, modalHeader, openModal } from '../../ui/modal.js';
import { startTimer } from './timer.js';

let userId = null;
let searchTimer = null;

export const initGamePicker = (id) => { userId = id; };

export const NOTES_MAX = 500; // width of game_timers.notes

const hint = (text) => html`<div class="modal-hint">${text}</div>`;
const thumb = (url) => (url
  ? html`<img src="${url}" alt="" class="modal-result-thumb" />`
  : html`<div class="modal-result-thumb-placeholder">🎮</div>`);

// Every step replaces the previous modal; the pending search dies with it.
function openStep(content) {
  closeAllModals();
  return openModal(content, { onClose: () => clearTimeout(searchTimer) });
}

// Debounced search box: calls search(query) 250ms after typing stops.
function bindSearch(modal, inputId, search, delay = 250) {
  const input = modal.el.querySelector(`#${inputId}`);
  input.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const query = input.value.trim();
    searchTimer = setTimeout(() => search(query), delay);
  });
  input.focus();
}

// ── Step 1: choose a game from the user's catalogue ─────────
export function openGamePicker(onPick) {
  const modal = openStep(html`
    ${modalHeader('Elegir juego')}
    <input type="text" id="gamePickerSearch" class="modal-search-input" placeholder="Buscar en tu catálogo..." autocomplete="off" />
    <div class="modal-results-list" id="gamePickerResults">${hint('Escribe para buscar un juego')}</div>
    <div class="modal-footer">
      <button class="btn-modal-secondary" id="modalAddGameBtn">${iconPlus()} ¿No está? Añadir nuevo juego</button>
    </div>`);
  modal.el.querySelector('#modalAddGameBtn').addEventListener('click', () => openAddGame(onPick));
  bindSearch(modal, 'gamePickerSearch', (query) => searchCatalogue(modal, query, onPick));
}

/** "Nuevo timer": pick a game, then its platform, then start. */
export const startTimerFlow = () => openGamePicker(chooseTimerPlatform);

async function searchCatalogue(modal, query, onPick) {
  const results = modal.el.querySelector('#gamePickerResults');
  if (query.length < 2) return mount(results, hint('Escribe al menos 2 caracteres'));
  mount(results, hint('Buscando...'));
  try {
    const games = await api(`/games/?name=${encodeURIComponent(query)}`);
    if (!results.isConnected) return; // modal closed while awaiting
    if (!games?.length) return mount(results, hint('Sin resultados en tu catálogo'));
    mount(results, html`${games.map((g) => html`
      <button class="modal-result-row" data-game-id="${g.id}">
        ${thumb(g.image_url)}<span class="modal-result-name">${g.name}</span>
      </button>`)}`);
    results.onclick = (e) => {
      const row = e.target.closest('.modal-result-row');
      if (!row) return;
      const game = games.find((g) => String(g.id) === row.dataset.gameId);
      closeAllModals();
      onPick(row.dataset.gameId, game?.name);
    };
  } catch (err) {
    if (results.isConnected) mount(results, hint(`Error buscando: ${err.message}`));
  }
}

// ── Step 1b: add a game from RAWG ───────────────────────────
function openAddGame(onPick) {
  const modal = openStep(html`
    ${modalHeader('Añadir juego nuevo')}
    <input type="text" id="addGameSearch" class="modal-search-input" placeholder="Buscar en RAWG..." autocomplete="off" />
    <div class="modal-results-list" id="addGameResults">${hint('Escribe el nombre del juego')}</div>`);
  bindSearch(modal, 'addGameSearch', (query) => searchRawg(modal, query, onPick), 300);
}

async function searchRawg(modal, query, onPick) {
  const results = modal.el.querySelector('#addGameResults');
  if (query.length < 2) return mount(results, hint('Escribe al menos 2 caracteres'));
  mount(results, hint('Buscando en RAWG...'));
  try {
    const candidates = await api(`/games/search-rawg?query=${encodeURIComponent(query)}`);
    if (!results.isConnected) return;
    if (!candidates?.length) return mount(results, hint('Sin resultados'));
    mount(results, html`${candidates.map((c, i) => html`
      <button class="modal-result-row" data-index="${i}">
        ${thumb(c.image_url)}
        <span class="modal-result-name">
          ${c.name}${c.released ? html` <span class="modal-result-year">(${c.released.slice(0, 4)})</span>` : ''}
          ${c.exists_in_db ? html`<span class="modal-result-badge">Ya en tu catálogo</span>` : ''}
        </span>
      </button>`)}`);
    results.onclick = (e) => {
      const row = e.target.closest('.modal-result-row');
      if (row) pickRawgCandidate(results, candidates[Number(row.dataset.index)], onPick);
    };
  } catch (err) {
    if (results.isConnected) mount(results, hint(`Error buscando: ${err.message}`));
  }
}

async function pickRawgCandidate(results, candidate, onPick) {
  try {
    if (candidate.exists_in_db && candidate.db_game_id) {
      closeAllModals();
      return onPick(candidate.db_game_id, candidate.name);
    }
    mount(results, hint('Añadiendo juego...'));
    const game = await api('/games/', jsonRequest('POST', {
      name: candidate.name,
      rawg_id: candidate.rawg_id,
      release_date: candidate.released || null,
      image_url: candidate.image_url || null,
      genres: (candidate.genres || []).join(','),
      slug: candidate.slug || null,
    }));
    closeAllModals();
    onPick(game.id, game.name);
  } catch (err) {
    if (results.isConnected) mount(results, hint(`Error: ${err.message}`));
  }
}

// ── Step 2: platform ────────────────────────────────────────
// Never played -> ask the platform; played before -> same platform or another one.
async function chooseTimerPlatform(gameId, gameName) {
  let info = { has_history: false, platforms: [] };
  try {
    info = (await api(`/timers/history/${userId}/platforms/${encodeURIComponent(gameId)}`)) || info;
  } catch (err) {
    console.error('Error fetching game platforms:', err);
  }
  openPlatformStep(gameId, gameName, info.platforms, false, info.has_history);
}

function platformRow(id, badge) {
  return html`
    <button class="modal-result-row" data-platform="${id}">
      <span class="modal-result-name">${platformName(id)}${badge ? html` <span class="modal-result-badge">${badge}</span>` : ''}</span>
    </button>`;
}

const notesField = () => html`<input type="text" id="timerNotes" class="modal-search-input" maxlength="${NOTES_MAX}" placeholder="Nota de la sesión (opcional)" autocomplete="off" />`;

function openPlatformStep(gameId, gameName, used, forceAll = false, hasHistory = used.length > 0) {
  const showAll = forceAll || used.length === 0; // no known platform to offer as "same"
  let content;

  if (showAll) {
    const message = forceAll
      ? 'Elige la nueva plataforma'
      : hasHistory
        ? 'Ya has jugado a este juego, pero no consta la plataforma. ¿En cuál juegas?'
        : 'Este juego es nuevo para ti. ¿En qué plataforma juegas?';
    const rows = platformList().map((p) => platformRow(p.id, used.includes(p.id) ? 'Ya usada' : ''));
    content = html`${hint(message)}${notesField()}<div class="modal-results-list">${rows.length ? rows : hint('No hay plataformas disponibles')}</div>`;
  } else {
    content = html`
      ${hint('Ya has jugado a este juego. ¿En qué plataforma?')}
      ${notesField()}
      <div class="modal-results-list">${used.map((id, i) => platformRow(id, i === 0 ? 'Misma que la última vez' : ''))}</div>
      <div class="modal-footer">
        <button class="btn-modal-secondary" id="otherPlatformBtn">${iconPlus()} Otra plataforma</button>
      </div>`;
  }

  const modal = openStep(html`${modalHeader(gameName || 'Plataforma')}${content}`);
  modal.el.querySelectorAll('[data-platform]').forEach((btn) => btn.addEventListener('click', () => {
    const notes = modal.el.querySelector('#timerNotes').value.trim() || null;
    closeAllModals();
    startTimer(gameId, btn.dataset.platform, notes);
  }));
  modal.el.querySelector('#otherPlatformBtn')?.addEventListener('click', () => openPlatformStep(gameId, gameName, used, true, hasHistory));
}
