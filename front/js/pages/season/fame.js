// The hall of fame of the Temporada page (#/season/fame), in three views of the same answer (GET /statistics/hall-of-fame):
// a row per season with a column per category, a cabinet per player with what they have won, or a timeline that puts the
// grand champion of each season first. Each player with titles
// keeps one colour in every view (the ring of their photo), so who dominates a season shows without reading names.
import { html } from '../../lib/html.js';
import { CATEGORIES, VIEWS, cabinets, grandChampions, playerHues, seasonsWithChampions, titleRanking, titlesText } from '../../lib/hall-of-fame.js';
import { playerAvatar } from '../../ui/avatar.js';

const hueClass = (hues, id) => `hf-h${hues.get(id) ?? 0}`;

const who = (hues, player, label = player.name) =>
  html`<span class="hf-who ${hueClass(hues, player.user_id)}">${playerAvatar(player)}<span class="ss-name">${label}</span></span>`;

// Who has won most titles, as a row of chips.
const lead = (answer, hues) => html`
  <div class="hf-lead" aria-label="Más títulos">${titleRanking(answer).map((t) => html`
    <span class="hf-chip ${hueClass(hues, t.user_id)}">${playerAvatar(t)}<b class="ss-name">${t.name}</b><span class="hf-count">${t.titles}</span></span>`)}
  </div>`;

// The cell of a category: the champion (every one on a tie) and the figure they share.
const cell = (category, hues, winners) => html`
  <td data-label="${category.short}">
    ${winners?.length
      ? html`<div class="hf-cell">${winners.map((w) => who(hues, w))}<span class="hf-figure">${category.text(winners[0].value)}</span></div>`
      : html`<span class="pf-sub">—</span>`}
  </td>`;

// The one who won most categories of the season: "👑 Jordi · 5 de 6".
const grand = (entry, hues) => {
  const { winners, wins, decided } = grandChampions(entry);
  if (!winners.length) return '';
  return html`<span class="hf-grand">👑 ${winners.map((w, i) => html`${i ? ' y ' : ''}<span class="hf-who ${hueClass(hues, w.user_id)}">${w.name}</span>`)} · ${wins} de ${decided}</span>`;
};

const matrix = (answer, hues) => html`
  ${lead(answer, hues)}
  <table class="hf-matrix">
    <thead><tr><th scope="col">Temporada</th>${CATEGORIES.map((c) => html`<th scope="col">${c.short}</th>`)}</tr></thead>
    <tbody>${seasonsWithChampions(answer).map((entry) => html`
      <tr aria-label="Temporada ${entry.season}">
        <th scope="row" class="hf-season"><span class="hf-year">${entry.season}</span>${grand(entry, hues)}</th>
        ${CATEGORIES.map((c) => cell(c, hues, entry.champions[c.id]))}
      </tr>`)}
    </tbody>
  </table>`;

// A cabinet: the player, their titles and, season by season, the categories they won.
const cabinet = (player, hues) => html`
  <section class="pf-card ss-card hf-card ${hueClass(hues, player.user_id)}" aria-label="${player.name}">
    <div class="hf-head">${playerAvatar(player)}<div><h2 class="ss-title">${player.name}</h2><span class="pf-sub">${titlesText(player.titles)}</span></div></div>
    <ul class="hf-trophies">${player.seasons.map((s) => html`
      <li><span class="hf-year">${s.season}</span>
        <span class="hf-medals">${s.categories.map((id) => html`<span class="hf-medal">${CATEGORIES.find((c) => c.id === id).short}</span>`)}</span></li>`)}
    </ul>
  </section>`;

const players = (answer, hues) => html`<div class="ss-grid hf-grid">${cabinets(answer).map((player) => cabinet(player, hues))}</div>`;

// A timeline, the newest season first: the grand champion large, then the champion of every category in small.
const step = (entry, hues) => {
  const { winners, wins, decided } = grandChampions(entry);
  return html`
    <li class="hf-step" aria-label="Temporada ${entry.season}">
      <span class="hf-dot" aria-hidden="true"></span>
      <div class="pf-card hf-step-body">
        <div class="hf-hero">
          <span class="hf-year hf-year-big">${entry.season}</span>
          ${winners.map((w) => html`<span class="hf-who hf-hero-who ${hueClass(hues, w.user_id)}">${playerAvatar(w)}<span class="hf-hero-name"><span class="ss-name">👑 ${w.name}</span><span class="pf-sub">${wins} de ${decided} categorías</span></span></span>`)}
        </div>
        <ul class="hf-others">${CATEGORIES.map((category) => html`
          <li><span class="hf-label">${category.title}</span>
            ${entry.champions[category.id]?.length
              ? html`${entry.champions[category.id].map((w) => who(hues, w))}<span class="hf-figure">${category.text(entry.champions[category.id][0].value)}</span>`
              : html`<span class="pf-sub">—</span>`}
          </li>`)}
        </ul>
      </div>
    </li>`;
};

const timeline = (answer, hues) => html`${lead(answer, hues)}<ol class="hf-timeline">${seasonsWithChampions(answer).map((entry) => step(entry, hues))}</ol>`;

const pills = (view) => html`
  <div class="pf-season" role="group" aria-label="Vista">${VIEWS.map(([id, label]) => html`
    <button type="button" class="pf-season-badge" data-fame-view="${id}" aria-pressed="${String(id === view)}">${label}</button>`)}
  </div>`;

/** The hall of fame in `view` ('matrix', 'players' or 'timeline'). */
export function fameView(answer, view) {
  if (!seasonsWithChampions(answer).length) return html`<div class="pf-empty">Todavía no ha terminado ninguna temporada con datos.</div>`;
  const hues = playerHues(answer);
  const views = { matrix, players, timeline };
  return html`${pills(view)}${(views[view] ?? matrix)(answer, hues)}`;
}
