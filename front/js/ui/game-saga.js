// "Saga" card of the game page: the games of the series of a game in order of release, with what you have of each one.
// GET /games/{id}/series asks RAWG (and the API keeps the answer for a day), so it is loaded apart, after the page is
// drawn; when there is no saga, or it cannot be loaded, the card is simply not there. It folds (a long saga is long),
// and the choice is remembered in this browser.
import { api } from '../lib/api.js';
import { html, mount } from '../lib/html.js';
import { gameHref } from '../lib/links.js';
import { newestFirst, releaseYear, sagaSummary, standing } from '../lib/saga.js';
import { iconChevron } from './icons.js';

const FOLDED_KEY = 'gm-saga-folded';

// Per-viewer convenience only: a browser that refuses storage just starts open.
const isFolded = () => {
  try {
    return localStorage.getItem(FOLDED_KEY) === '1';
  } catch {
    return false;
  }
};

const rememberFolded = (folded) => {
  try {
    localStorage.setItem(FOLDED_KEY, folded ? '1' : '0');
  } catch {
    // nothing to do: it is not remembered
  }
};

function row(g) {
  const state = standing(g);
  const name = g.game_id
    ? html`<a class="game-link" href="${gameHref(g.game_id)}">${g.name}</a>`
    : g.slug
      ? html`<a class="game-link" href="https://rawg.io/games/${encodeURIComponent(g.slug)}" target="_blank" rel="noopener noreferrer">${g.name}</a>`
      : g.name;
  return html`
    <li class="sg-game ${g.current ? 'current' : ''}" data-rawg="${g.rawg_id}">
      <span class="sg-year pf-sub">${releaseYear(g.released) || '—'}</span>
      <div class="sg-main">
        <div>${name}
          ${g.current ? html`<span class="pf-tag">Esta página</span>` : ''}
          ${g.next ? html`<span class="pf-tag live">Siguiente</span>` : ''}
        </div>
        <div class="pf-sub"><span class="pf-tag ${state.tone}">${state.label}</span>${g.players ? ` · ${g.players === 1 ? '1 jugador lo tiene' : `${g.players} jugadores lo tienen`}` : ''}</div>
      </div>
    </li>`;
}

/** Fill `el` with the saga of the game; nothing at all when there is none. */
export async function showSaga(el, gameId) {
  let data;
  try {
    data = await api(`/games/${encodeURIComponent(gameId)}/series`);
  } catch {
    return;
  }
  if (!data?.available || !data.games.length) return;
  const folded = isFolded();
  mount(el, html`
    <section class="ach-block ${folded ? 'folded' : ''}" id="gmSagaBlock">
      <button type="button" class="section-header ach-fold" data-fold aria-expanded="${String(!folded)}">
        <h2 class="section-title">Saga</h2><span class="pf-sub sg-count">${data.games.length}</span><div class="section-line"></div><span class="ach-chevron" aria-hidden="true">${iconChevron()}</span>
      </button>
      <div class="ach-content">
        <div class="pf-card">
          <div class="pf-sub sg-summary">${sagaSummary(data.games)}</div>
          <ol class="sg-games">${newestFirst(data.games).map(row)}</ol>
        </div>
      </div>
    </section>`);
  el.onclick = (e) => {
    const fold = e.target.closest('[data-fold]');
    if (!fold) return;
    const block = el.querySelector('#gmSagaBlock');
    const nowFolded = !block.classList.contains('folded');
    block.classList.toggle('folded', nowFolded);
    fold.setAttribute('aria-expanded', String(!nowFolded));
    rememberFolded(nowFolded);
  };
}
