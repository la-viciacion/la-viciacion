// The pieces of a player's summary shared by the profile and the public player page: the season pills, the figures,
// the most played games and the latest achievements. `d` is what GET .../profile answers.
import { formatDate, formatDuration } from '../lib/format.js';
import { html } from '../lib/html.js';
import { gameHref } from '../lib/links.js';
import * as seasons from '../lib/seasons.js';
import { scoreBadge } from './score-badge.js';

export const statTile = (label, value) => html`
  <div class="pf-stat"><div class="pf-stat-value">${value}</div><div class="pf-stat-label">${label}</div></div>`;

export const titleView = (title) => html`<h2 class="section-title">${title}</h2><div class="section-line"></div>`;
export const sectionTitle = (title, id) => html`<div class="section-header" ${id ? html`id="${id}"` : ''}>${titleView(title)}</div>`;

export const seasonName = (d) => (d.season === seasons.ALL ? 'todas las temporadas' : `temporada ${d.season}`);
export const seasonSuffix = (d) => (d.season === seasons.ALL ? '(total)' : `en ${d.season}`);

export function seasonPills(d) {
  return html`${seasons.choices(d.seasons).map(({ value, label }) => html`
    <button type="button" class="pf-season-badge" data-season="${value}" aria-pressed="${String(value === d.season)}">${value === seasons.ALL ? label : `Temporada ${label}`}</button>`)}`;
}

export function statsView(d) {
  const s = d.stats;
  // a streak that is still running only makes sense for the running season or the total
  const running = d.season === seasons.ALL || d.season === d.seasons[0];
  return html`
    ${statTile('Tiempo jugado', formatDuration(s.played_time))}
    ${statTile('Días jugados', s.played_days)}
    ${statTile('Juegos jugados', s.played_games)}
    ${statTile('Completados', s.completed_games)}
    ${running ? statTile('Racha actual', `${s.current_streak} d`) : ''}
    ${statTile('Mejor racha', `${s.best_streak} d`)}
    ${statTile('Logros', s.achievements)}`;
}

function topGameRow(g, max) {
  const width = Math.max(3, Math.round((g.played_time / max) * 100));
  return html`
    <div class="pf-bar-row">
      <div class="pf-bar-label"><span><a class="game-link" href="${gameHref(g.game_id)}">${g.game_name}</a> ${scoreBadge(g.score)}</span><span>${formatDuration(g.played_time)}</span></div>
      <div class="pf-bar"><div style="width:${width}%"></div></div>
    </div>`;
}

export function topView(d) {
  const max = Math.max(1, ...d.top_games.map((g) => g.played_time));
  return d.top_games.length
    ? html`${d.top_games.map((g) => topGameRow(g, max))}`
    : html`<div class="pf-empty">Aún no hay tiempo registrado.</div>`;
}

/** `own`: it is the viewer's own profile ("no has conseguido") and not somebody else's. */
export function achievementsView(d, own = true) {
  return d.achievements.length
    ? html`${d.achievements.map((a) => html`<div class="pf-row"><div class="pf-row-main">${a.hidden ? html`<em>Logro oculto</em>` : html`<strong>${a.title}</strong>`}</div><div class="pf-sub">${formatDate(a.date)}</div></div>`)}`
    : html`<div class="pf-empty">${own ? 'Todavía no has conseguido logros.' : 'Todavía no ha conseguido logros.'}</div>`;
}
