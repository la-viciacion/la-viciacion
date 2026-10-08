// Statistics (#/stats): the figures of one player of the group, picked from a dropdown, for a season or for all of them,
// or, for the whole group, bar charts of hours and games and a line chart of the hours day by day. GET /group/players
// (the dropdown), GET /group/players/{id}?season= and GET /activity (the days of the line chart; derived, nothing stored).
import { api } from '../../lib/api.js';
import { cumulativeSeries } from '../../lib/daily.js';
import { formatDate, formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import * as seasons from '../../lib/seasons.js';
import { achievementsView, sectionTitle, seasonName, seasonPills, seasonSuffix, statTile, statsView, topView } from '../../ui/profile-summary.js';
import { feedSince, resetFeed } from './feed.js';
import { lineChart } from './line-chart.js';

export const active = null; // it belongs to no item of the top bar

let main;
let playerId;
let shown = null; // the season asked for: a year, seasons.ALL, or null = the running one
let latest = 0; // an answer to an older request must not replace a newer one

const EVERYBODY = 'all'; // the dropdown value that adds the whole group up

let players = [];

const optionLabel = (p) => `${p.name}${p.is_me ? ' (tú)' : ''}${p.is_active ? '' : ' (inactivo)'}`;

const sum = (key) => players.filter((p) => p.is_active).reduce((total, p) => total + p[key], 0);

const query = () => (shown == null ? '' : `?season=${shown}`);

const barRow = (p, value, label, max) => html`
  <div class="pf-bar-row">
    <div class="pf-bar-label"><span>${p.name}${p.is_me ? ' (tú)' : ''}</span><span>${label}</span></div>
    <div class="pf-bar"><div style="width:${Math.max(3, Math.round((value / max) * 100))}%"></div></div>
  </div>`;

// One bar per player, the most first, for the figure `key` of each one
const chart = (title, rows, key, format) => {
  const sorted = [...rows].sort((a, b) => b[key] - a[key]);
  const max = Math.max(1, ...sorted.map((p) => p[key]));
  return html`
    <section class="st-block">
      ${sectionTitle(title)}
      <div class="pf-card">${sorted.map((p) => barRow(p, p[key], format(p[key]), max))}</div>
    </section>`;
};

const gamesLabel = (n) => `${n} ${n === 1 ? 'juego' : 'juegos'}`;

const evolution = ({ line, truncated }, d) => html`
  <section class="st-block">
    ${sectionTitle(`Evolución de las horas ${seasonSuffix(d)}`)}
    <div class="pf-card">
      ${line && line.days.length > 1
        ? html`<div class="pf-sub">Horas acumuladas de cada jugador, día a día.</div>${lineChart(line)}`
        : html`<div class="pf-empty">Todavía no hay días suficientes para dibujar la evolución.</div>`}
      ${truncated && line ? html`<div class="pf-sub">El historial es muy largo: el gráfico empieza el ${formatDate(line.days[0])}.</div>` : ''}
    </div>
  </section>`;

// The added-up figures are the players' own totals (every season), so they only show with the Total pill
const drawGroup = ({ rows, ...rest }) => {
  const d = { season: shown ?? seasons.current(), seasons: seasons.available() };
  return html`
    <div class="pf-season" role="group" aria-label="Temporada">${seasonPills(d)}</div>
    ${chart(`Horas jugadas ${seasonSuffix(d)}`, rows, 'played_seconds', formatDuration)}
    ${chart(`Juegos jugados ${seasonSuffix(d)}`, rows, 'played_games', gamesLabel)}
    ${evolution(rest, d)}
    ${d.season === seasons.ALL ? html`
      <section class="pf-stats" aria-label="Estadísticas: todos los jugadores">
        ${statTile('Tiempo jugado', formatDuration(sum('played_seconds')))}
        ${statTile('Juegos jugados (suma)', sum('games'))}
        ${statTile('Completados', sum('completed'))}
      </section>` : ''}`;
};

const drawPlayer = (d) => html`
  <div class="pf-season" role="group" aria-label="Temporada">${seasonPills(d)}</div>
  <section class="pf-stats" aria-label="Estadísticas: ${seasonName(d)}">${statsView(d)}</section>
  <div class="pf-cols">
    <div>
      ${sectionTitle(`Más jugados ${seasonSuffix(d)}`)}
      <div class="pf-card">${topView(d)}</div>
    </div>
    <div>
      ${sectionTitle(`Logros ${seasonSuffix(d)}`)}
      <div class="pf-card">${achievementsView(d, d.is_me)}</div>
    </div>
  </div>`;

const playerPath = (id) => `/group/players/${encodeURIComponent(id)}${query()}`;

// The figures of each active player in the season, from the same page of each player the dropdown opens
async function groupFigures() {
  const active = players.filter((p) => p.is_active);
  const pages = await Promise.all(active.map((p) => api(playerPath(p.user_id))));
  if (pages.includes(undefined)) return undefined; // the session ended (401)
  return active.map((p, i) => ({
    user_id: p.user_id, name: p.name, is_me: p.is_me, played_seconds: pages[i].stats.played_time, played_games: pages[i].stats.played_games,
  }));
}

async function groupData() {
  const rows = await groupFigures();
  const season = shown === seasons.ALL ? null : shown ?? seasons.current();
  const feed = await feedSince(season === null ? null : `${season}-01-01`);
  if (!rows || !feed) return undefined;
  return { rows, line: cumulativeSeries(feed.items, rows, season), truncated: feed.truncated };
}

async function load() {
  const target = main.querySelector('#stData');
  const mine = ++latest;
  const group = playerId === EVERYBODY;
  try {
    const data = await (group ? groupData() : api(playerPath(playerId)));
    if (!data || mine !== latest) return;
    mount(target, group ? drawGroup(data) : drawPlayer(data));
  } catch (err) {
    if (mine !== latest) return;
    mount(target, html`<div class="pf-empty">Error cargando las estadísticas: ${err.message}</div>`);
  }
}

export async function render(ctx) {
  main = ctx.main;
  shown = null;
  resetFeed();
  mount(main, html`
    <h1 class="pf-title pg-title">Estadísticas</h1>
    <div id="stPick"></div>
    <div id="stData"><div class="loading-spinner">Cargando estadísticas...</div></div>`);
  try {
    const list = await api('/group/players');
    if (!list) return;
    if (!list.length) {
      mount(main.querySelector('#stData'), html`<div class="pf-empty">Todavía no hay jugadores.</div>`);
      return;
    }
    players = list;
    playerId = (list.find((p) => p.is_me) || list[0]).user_id;
    mount(main.querySelector('#stPick'), html`
      <div class="gc-toolbar">
        <select class="adm-input" id="stPlayer" aria-label="Jugador"><option value="${EVERYBODY}">Todos los jugadores</option>${list.map((p) => html`
          <option value="${p.user_id}" ${p.user_id === playerId ? 'selected' : ''}>${optionLabel(p)}</option>`)}
        </select>
      </div>`);
  } catch (err) {
    mount(main.querySelector('#stData'), html`<div class="pf-empty">Error cargando los jugadores: ${err.message}</div>`);
    return;
  }
  main.querySelector('#stPlayer').addEventListener('change', (e) => {
    playerId = e.target.value === EVERYBODY ? EVERYBODY : Number(e.target.value);
    shown = null;
    load();
  });
  main.querySelector('#stData').addEventListener('click', (e) => {
    const pill = e.target.closest('[data-season]');
    if (!pill || pill.getAttribute('aria-pressed') === 'true') return;
    shown = pill.dataset.season === seasons.ALL ? seasons.ALL : Number(pill.dataset.season);
    load();
  });
  await load();
}
