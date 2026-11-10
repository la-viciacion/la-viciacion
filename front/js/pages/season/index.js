// Season page (#/season): the rankings of the running season (active players only). It always shows the current season
// (there is no selector). One request (GET /statistics/rankings); everything is derived from the sessions, the library and
// the achievements: nothing is stored. Each ranking has its own way of being drawn (`view` in lib/season-stats.js): a podium,
// bars, tiles, rings or game covers.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { RANKINGS, barWidths, podiumOrder, positions, rankingsPath, ringPercent, rowsOf } from '../../lib/season-stats.js';
import { current } from '../../lib/seasons.js';
import { hydratePhotos, playerAvatar } from '../../ui/avatar.js';

export const active = null; // it belongs to no item of the top bar

const SHOWN = 10;
const MEDALS = ['🥇', '🥈', '🥉'];
const medal = (place) => MEDALS[place - 1] ?? place;
const tier = (place) => `place-${Math.min(place, 4)}`;

const cover = (e, big) => (e.image_url
  ? html`<img class="ss-cover${big ? ' big' : ''}" src="${e.image_url}" alt="" loading="lazy" />`
  : html`<div class="ss-cover${big ? ' big' : ''} ss-cover-empty" aria-hidden="true">🎮</div>`);

// What stands at the left of a line or a step: the cover of a game, the avatar of a player.
const lead = (ranking, e, big) => (ranking.rows === 'games' ? cover(e, big) : playerAvatar(e));

// A line with the name, the value and a bar; what stands at its left (an avatar, a cover) is `lead`.
const line = (ranking, e, place, width, lead) => html`
  <li class="ss-row">
    <span class="ss-place" aria-label="Puesto ${place}">${medal(place)}</span>
    ${lead}
    <div class="ss-main">
      <div class="ss-line">
        ${ranking.rows === 'games'
          ? html`<a class="game-link ss-name" href="${gameHref(e.game_id)}">${e.name}</a>`
          : html`<span class="ss-name">${e.name}</span>`}
        <strong class="ss-value">${ranking.text(e)}</strong>
      </div>
      <div class="ss-bar" aria-hidden="true"><div class="ss-fill ${tier(place)}" style="width: ${width}%"></div></div>
    </div>
  </li>`;

const bars = (ranking, rows, widths, places, from = 0) => html`
  <ol class="ss-list" start="${from + 1}">${rows.slice(from).map((e, i) => line(ranking, e, places[from + i], widths[from + i], lead(ranking, e, false)))}</ol>`;

// The first three on a podium (second, first, third), the others as bars under it.
const podium = (ranking, rows, widths, places) => html`
  <div class="ss-podium">
    ${podiumOrder(rows).map((i) => html`
      <div class="ss-step ${tier(places[i])}">
        <span class="ss-medal">${medal(places[i])}</span>
        ${lead(ranking, rows[i], true)}
        ${ranking.rows === 'games'
          ? html`<a class="game-link ss-name" href="${gameHref(rows[i].game_id)}">${rows[i].name}</a>`
          : html`<span class="ss-name">${rows[i].name}</span>`}
        <strong class="ss-value">${ranking.text(rows[i])}</strong>
        <div class="ss-pedestal" aria-hidden="true"></div>
      </div>`)}
  </div>
  ${rows.length > 3 ? bars(ranking, rows, widths, places, 3) : ''}`;

// Big numbers: the value in large type, the name under it.
const tiles = (ranking, rows, places) => html`
  <ul class="ss-tiles">
    ${rows.map((e, i) => html`
      <li class="ss-tile ${tier(places[i])}">
        <span class="ss-tile-place">${medal(places[i])}</span>
        ${playerAvatar(e)}
        <strong class="ss-big">${ranking.icon ? html`<span aria-hidden="true">${ranking.icon}</span> ` : ''}${ranking.value(e)}</strong>
        <span class="ss-unit">${ranking.unit}</span>
        <span class="ss-name">${e.name}</span>
      </li>`)}
  </ul>`;

// A ring filled as far as the ratio goes.
const rings = (ranking, rows, places) => html`
  <ul class="ss-tiles">
    ${rows.map((e, i) => html`
      <li class="ss-tile">
        <div class="ss-ring ${tier(places[i])}" style="--p: ${ringPercent(ranking.value(e))}%" role="img" aria-label="${ranking.text(e)}">
          <span>${ranking.text(e)}</span>
        </div>
        <span class="ss-name">${medal(places[i])} ${e.name}</span>
      </li>`)}
  </ul>`;

// The games with their cover, the first one larger.
const covers = (ranking, rows, widths, places) => html`
  <ol class="ss-list ss-covers">${rows.map((e, i) => line(ranking, e, places[i], widths[i], lead(ranking, e, i === 0)))}</ol>`;

const VIEWS = {
  bars: (ranking, rows, widths, places) => bars(ranking, rows, widths, places),
  podium,
  tiles: (ranking, rows, widths, places) => tiles(ranking, rows, places),
  rings: (ranking, rows, widths, places) => rings(ranking, rows, places),
  covers,
};

const card = (ranking, answer) => {
  const rows = rowsOf(answer, ranking).slice(0, SHOWN);
  return html`
    <section class="pf-card ss-card ss-${ranking.view}-card" id="ss-${ranking.id}" aria-label="${ranking.title}">
      <h2 class="ss-title">${ranking.title}</h2>
      ${rows.length
        ? VIEWS[ranking.view](ranking, rows, barWidths(rows, ranking), positions(rows, ranking))
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
