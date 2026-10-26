// A search box for a game of the catalogue inside a form (GET /games/catalog?q=): what the player types lists the games
// that match and choosing one leaves it in `state.game` ({ id, name }). Markup and behaviour go together: put
// `gameSearchField` in the form and call `gameSearch` once it is on the page.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';

export const gameSearchField = html`
  <label>Juego<input class="adm-input" type="search" name="gameQuery" placeholder="Buscar juego..." autocomplete="off" /></label>
  <div class="ch-game-results" data-game-results></div>
  <p class="adm-sub" data-game-chosen aria-live="polite">Elige un juego de la lista.</p>`;

export function gameSearch(form, state) {
  const results = form.querySelector('[data-game-results]');
  const chosen = form.querySelector('[data-game-chosen]');
  let timer;
  form.elements.gameQuery.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const query = form.elements.gameQuery.value.trim();
      if (query.length < 2) return mount(results, html``);
      try {
        const found = await api(`/games/catalog?q=${encodeURIComponent(query)}&limit=8`);
        mount(results, html`${found.items.map((g) => html`<button type="button" class="pf-btn" data-game-id="${g.id}" data-game-name="${g.name}">${g.name}</button>`)}`);
      } catch (err) {
        mount(results, html`<div class="pf-empty">${err.message}</div>`);
      }
    }, 250);
  });
  results.addEventListener('click', (e) => {
    const pick = e.target.closest('[data-game-id]');
    if (!pick) return;
    state.game = { id: pick.dataset.gameId, name: pick.dataset.gameName };
    chosen.textContent = `Juego elegido: ${state.game.name}`;
    mount(results, html``);
  });
}
