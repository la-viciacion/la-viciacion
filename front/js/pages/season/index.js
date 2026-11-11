// Season page (#/season[/<year>]): the rankings of a season (the active players for the running one, everybody who took part for an older one), the running one by default, with a pill
// per season to look at the older ones. One request (GET /statistics/rankings?season=); everything is derived from the
// sessions, the library and the achievements: nothing is stored. Each ranking has its own way of being drawn (`view` in lib/season-stats.js): a podium,
// bars, tiles, rings or game covers.
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { CATEGORIES, FAME, seasonsWithChampions, titleRanking, titlesText } from '../../lib/hall-of-fame.js';
import { barWidths, isFameHash, participantsOf, podiumOrder, positions, rankingsOf, rankingsPath, ringPercent, rowsOf, seasonFromHash } from '../../lib/season-stats.js';
import { available, current } from '../../lib/seasons.js';
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

const card = (ranking, answer, players) => {
  const rows = rowsOf(answer, ranking, players).slice(0, SHOWN);
  return html`
    <section class="pf-card ss-card ss-${ranking.view}-card" id="ss-${ranking.id}" aria-label="${ranking.title}">
      <h2 class="ss-title">${ranking.title}</h2>
      ${rows.length
        ? VIEWS[ranking.view](ranking, rows, barWidths(rows, ranking), positions(rows, ranking))
        : html`<div class="pf-empty">Todavía no hay datos.</div>`}
    </section>`;
};

const header = (season) => html`
  <h1 class="pf-title pg-title">${season === FAME ? 'Salón de la fama' : `Temporada ${season}`}</h1>
  <div class="pf-season" role="group" aria-label="Temporada">${available().map((year) => html`
    <button type="button" class="pf-season-badge" data-season="${year}" aria-pressed="${String(year === season)}">${year}</button>`)}
    <button type="button" class="pf-season-badge" data-season="${FAME}" aria-pressed="${String(season === FAME)}">Salón de la fama</button>
  </div>`;

// A winner of a category: the photo, the name and the figure.
const winner = (category, w) => html`
  <li class="hf-winner">${playerAvatar(w)}<span class="ss-name">${w.name}</span><strong class="ss-value">${category.text(w.value)}</strong></li>`;

const seasonCard = (entry) => html`
  <section class="pf-card ss-card hf-card" aria-label="Temporada ${entry.season}">
    <h2 class="ss-title">Temporada ${entry.season}</h2>
    <dl class="hf-list">
      ${CATEGORIES.map((category) => html`
        <div class="hf-row">
          <dt>${category.title}</dt>
          <dd>${entry.champions[category.id]?.length
            ? html`<ul class="hf-winners">${entry.champions[category.id].map((w) => winner(category, w))}</ul>`
            : html`<span class="pf-sub">—</span>`}</dd>
        </div>`)}
    </dl>
  </section>`;

// The players with most titles, then the seasons one by one, the newest first.
function fame(answer) {
  const history = seasonsWithChampions(answer);
  if (!history.length) return html`<div class="pf-empty">Todavía no ha terminado ninguna temporada con datos.</div>`;
  const titles = titleRanking(answer).slice(0, SHOWN);
  return html`
    <section class="pf-card ss-card hf-card" aria-label="Más títulos">
      <h2 class="ss-title">Más títulos</h2>
      <ol class="ss-list">${titles.map((t, i) => html`
        <li class="ss-row"><span class="ss-place" aria-label="Puesto ${i + 1}">${medal(i + 1)}</span>${playerAvatar(t)}<span class="ss-name">${t.name}</span><strong class="ss-value">${titlesText(t.titles)}</strong></li>`)}
      </ol>
    </section>
    <div class="ss-grid hf-grid">${history.map(seasonCard)}</div>`;
}

export async function render({ main }) {
  let latest = 0; // an answer to a season left meanwhile must not replace the one on screen

  async function show(season) {
    const mine = ++latest;
    mount(main, html`${header(season)}<div class="pf-empty">Cargando…</div>`);
    let answer;
    try {
      answer = await api(season === FAME ? '/statistics/hall-of-fame' : rankingsPath(season));
    } catch {
      if (mine === latest) mount(main, html`${header(season)}<div class="pf-empty">No se han podido cargar los rankings.</div>`);
      return;
    }
    if (mine !== latest) return;
    if (season === FAME) {
      mount(main, html`${header(season)}${fame(answer)}`);
      hydratePhotos(main);
      return;
    }
    const rankings = rankingsOf(season);
    // an older season lists everybody who took part, active today or not
    const players = season === current() ? null : participantsOf(answer, rankings);
    mount(main, html`
      ${header(season)}
      <div class="ss-grid">${rankings.map((ranking) => card(ranking, answer, players))}</div>`);
    hydratePhotos(main);
  }

  main.addEventListener('click', (e) => {
    const pill = e.target.closest('[data-season]');
    if (!pill || pill.getAttribute('aria-pressed') === 'true') return;
    const season = pill.dataset.season === FAME ? FAME : Number(pill.dataset.season);
    // the address follows the pill (so it can be shared) without going through the router again
    history.replaceState(null, '', season === current() ? '#/season' : `#/season/${season}`);
    show(season);
  });
  await show(isFameHash(location.hash) ? FAME : seasonFromHash(location.hash));
}
