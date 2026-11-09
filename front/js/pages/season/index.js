// Season page (#/season): the rankings of the running season (active players only), drawn as bars. It always
// shows the current season (there is no selector). One request (GET /statistics/rankings); everything is derived from the
// sessions, the library and the achievements: nothing is stored.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { RANKINGS, barWidths, positions, rankingsPath, rowsOf, visibleRows } from '../../lib/season-stats.js';
import { current } from '../../lib/seasons.js';
import { hydratePhotos, playerAvatar } from '../../ui/avatar.js';

export const active = null; // it belongs to no item of the top bar

const SHOWN = 10;
const MEDALS = ['🥇', '🥈', '🥉'];

const row = (ranking, e, place, width) => html`
  <li class="ss-row">
    <span class="ss-place" aria-label="Puesto ${place}">${MEDALS[place - 1] ?? place}</span>
    ${ranking.rows === 'games' ? '' : playerAvatar(e)}
    <div class="ss-main">
      <div class="ss-line">
        ${ranking.rows === 'games'
          ? html`<a class="game-link ss-name" href="${gameHref(e.game_id)}">${e.name}</a>`
          : html`<span class="ss-name">${e.name}</span>`}
        <strong class="ss-value">${ranking.text(e)}</strong>
      </div>
      <div class="ss-bar" aria-hidden="true"><div class="ss-fill place-${Math.min(place, 4)}" style="width: ${width}%"></div></div>
    </div>
  </li>`;

const card = (ranking, answer) => {
  const rows = visibleRows(rowsOf(answer, ranking), ranking, SHOWN);
  const widths = barWidths(rows, ranking);
  const places = positions(rows, ranking);
  return html`
    <section class="pf-card ss-card" id="ss-${ranking.id}" aria-label="${ranking.title}">
      <h2 class="ss-title">${ranking.title}</h2>
      <div class="pf-sub">${ranking.sub}</div>
      ${rows.length
        ? html`<ol class="ss-list">${rows.map((e, i) => row(ranking, e, places[i], widths[i]))}</ol>`
        : html`<div class="pf-empty">Todavía no hay datos.</div>`}
    </section>`;
};

const title = html`<h1 class="pf-title pg-title">Temporada ${current()}</h1>`;

export async function render({ main }) {
  mount(main, html`${title}<div class="pf-empty">Cargando…</div>`);
  let answer;
  try {
    answer = await api(rankingsPath());
  } catch {
    mount(main, html`${title}<div class="pf-empty">No se han podido cargar los rankings.</div>`);
    return;
  }
  mount(main, html`
    ${title}
    <div class="ss-grid">${RANKINGS.map((ranking) => card(ranking, answer))}</div>`);
  hydratePhotos(main);
}
