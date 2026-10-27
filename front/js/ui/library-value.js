// "Lo que has gastado" of Mis juegos: what the player paid for their games and what it comes to per hour, in total and
// game by game (the cheapest and the dearest per hour). GET /users/{username}/value: derived from the prices the player
// noted and their hours, and only theirs (the group sees a mean cost per hour of a game, never anybody's price).
import { api } from '../lib/api.js';
import { formatDuration } from '../lib/format.js';
import { html, mount } from '../lib/html.js';
import { gameHref } from '../lib/links.js';
import { euros, perHour } from '../lib/money.js';

const SHOWN = 5;

const tile = (label, value) => html`<div class="pf-stat"><div class="pf-stat-value">${value}</div><div class="pf-stat-label">${label}</div></div>`;

function list(title, games) {
  if (!games.length) return '';
  return html`
    <div class="pv-list">
      <h3>${title}</h3>
      ${games.map((g) => html`
        <div class="pv-item"><a class="game-link" href="${gameHref(g.game_id)}">${g.game_name}</a>
          <div class="pf-sub">${perHour(g.per_hour_cents)} · ${euros(g.price_cents)} por ${formatDuration(g.seconds)}</div></div>`)}
    </div>`;
}

/** Fill `el` with the player's value summary; nothing at all when they noted no price (or it cannot be loaded). */
export async function showValue(el, username) {
  let data;
  try {
    data = await api(`/users/${encodeURIComponent(username)}/value`);
  } catch {
    return;
  }
  if (!data?.priced_games) return mount(el, html``);
  const counted = data.games.filter((g) => g.per_hour_cents != null);
  mount(el, html`
    <details class="pf-card pf-value" open>
      <summary><strong>Lo que has gastado</strong> <span class="pf-sub">Solo lo ves tú</span></summary>
      <section class="pf-stats" aria-label="Lo que has gastado">
        ${tile('Gastado', euros(data.spent_cents))}
        ${tile(`Juegos con precio (${data.counted_games} con tiempo)`, data.priced_games)}
        ${tile('Coste medio por hora', data.per_hour_cents == null ? '—' : perHour(data.per_hour_cents))}
      </section>
      <div class="pv-lists">
        ${list('Más rentables', counted.slice(0, SHOWN))}
        ${counted.length > SHOWN ? list('Menos rentables', [...counted].reverse().slice(0, SHOWN)) : ''}
      </div>
      <div class="pf-sub">El coste por hora cuenta los juegos con al menos media hora jugada.</div>
    </details>`);
}
