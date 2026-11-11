// The hall of fame of the Temporada page (#/season/fame), from GET /statistics/hall-of-fame: a timeline with a step per
// closed season, the newest first. Each step puts the grand champion of the season large and, under it, the champion of
// every category in a cell of the same size. Each player with titles keeps one colour (the ring of their photo), so who
// dominates a season shows without reading names.
import { html } from '../../lib/html.js';
import { CATEGORIES, grandChampions, playerHues, seasonsWithChampions, titleRanking } from '../../lib/hall-of-fame.js';
import { playerAvatar } from '../../ui/avatar.js';

const hueClass = (hues, id) => `hf-h${hues.get(id) ?? 0}`;

const who = (hues, player) =>
  html`<span class="hf-who ${hueClass(hues, player.user_id)}">${playerAvatar(player)}<span class="ss-name">${player.name}</span></span>`;

// Who has won most titles, as a row of chips.
const lead = (answer, hues) => html`
  <div class="hf-lead" aria-label="Más títulos">${titleRanking(answer).map((t) => html`
    <span class="hf-chip ${hueClass(hues, t.user_id)}">${playerAvatar(t)}<b class="ss-name">${t.name}</b><span class="hf-count">${t.titles}</span></span>`)}
  </div>`;

// The champion of a category (every one on a tie) and the figure they share; the label is one line, so the cells line up.
const cell = (category, hues, winners) => html`
  <li>
    <span class="hf-label">${category.short}</span>
    ${winners?.length
      ? html`<div class="hf-winners">${winners.map((w) => who(hues, w))}</div><span class="hf-figure">${category.text(winners[0].value)}</span>`
      : html`<span class="pf-sub">—</span>`}
  </li>`;

const step = (entry, hues) => {
  const { winners, wins, decided } = grandChampions(entry);
  return html`
    <li class="hf-step" aria-label="Temporada ${entry.season}">
      <span class="hf-dot" aria-hidden="true"></span>
      <div class="pf-card hf-step-body">
        <div class="hf-hero">
          <span class="hf-year">${entry.season}</span>
          ${winners.map((w) => html`<span class="hf-who hf-hero-who ${hueClass(hues, w.user_id)}">${playerAvatar(w)}<span class="hf-hero-name"><span class="ss-name">👑 ${w.name}</span><span class="pf-sub">${wins} de ${decided} categorías</span></span></span>`)}
        </div>
        <ul class="hf-others">${CATEGORIES.map((category) => cell(category, hues, entry.champions[category.id]))}</ul>
      </div>
    </li>`;
};

/** The hall of fame: who has most titles and a step per closed season. */
export function fameView(answer) {
  const history = seasonsWithChampions(answer);
  if (!history.length) return html`<div class="pf-empty">Todavía no ha terminado ninguna temporada con datos.</div>`;
  const hues = playerHues(answer);
  return html`${lead(answer, hues)}<ol class="hf-timeline">${history.map((entry) => step(entry, hues))}</ol>`;
}
