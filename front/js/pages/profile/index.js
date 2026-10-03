// Profile page: a header with the stats of a season (the running one, another one or the total of
// all, chosen with the pills) and three tabs so nothing needs a long scroll: Resumen (top games,
// achievements and, below them, the games of the selected season: see library.js),
// Recomendados (see recommendations.js) and Ajustes (personal data, reminders, push
// notifications, password). The recommendations and the settings load the first time their tab
// is opened.
// All routes are /api/v1/users/{username}/...
import { api } from '../../lib/api.js';
import { formatDate, formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { PASSWORD_HINT } from '../../lib/password.js';
import * as seasons from '../../lib/seasons.js';
import { scoreBadge } from '../../ui/score-badge.js';
import { initAccount } from './account.js';
import { initAvatar } from './avatar.js';
import { flash } from './flash.js';
import { initLibrary, showSeason } from './library.js';
import { initPreferences } from './preferences.js';
import { initPush } from './push.js';
import { initRecommendations } from './recommendations.js';

export const active = 'profile';
export const mainClass = 'profile-main';

const TABS = [
  ['resumen', 'Resumen'],
  ['recomendados', 'Recomendados'],
  ['ajustes', 'Ajustes'],
];

let main;
let user;
let avatarUrl;
let opened; // tabs already initialised
let shown; // season asked for: a year, or seasons.ALL; null = the running one
let onScreen; // season on screen once resolved: a year, or seasons.ALL

const userPath = (suffix) => `/users/${encodeURIComponent(user.username)}/${suffix}`;

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  avatarUrl = ctx.avatarUrl;
  await load();
}

async function load() {
  const data = await api(userPath('profile'));
  if (!data) return;
  shown = null;
  onScreen = data.season;
  draw(data);
  opened = new Set();
  showTab(tabFromHash());
}

const tabFromHash = () => {
  const id = location.hash.split('/')[2];
  return TABS.some(([tab]) => tab === id) ? id : TABS[0][0];
};

// Tabs do not touch the router: replaceState changes the URL without a hashchange.
function showTab(id) {
  main.querySelectorAll('.pf-tab').forEach((tab) => {
    const on = tab.dataset.tab === id;
    tab.classList.toggle('active', on);
    tab.setAttribute('aria-selected', String(on));
    tab.tabIndex = on ? 0 : -1;
  });
  main.querySelectorAll('.pf-panel').forEach((panel) => { panel.hidden = panel.id !== `pfPanel-${id}`; });
  history.replaceState(null, '', `#/profile/${id}`);
  if (opened.has(id)) return;
  opened.add(id);
  if (id === 'resumen') initLibrary(main.querySelector('#pfLibrary'), { username: user.username, userId: user.id, season: onScreen, onChange: refreshSummary });
  if (id === 'recomendados') initRecommendations(main.querySelector('#pfRecommended'), { username: user.username });
  if (id === 'ajustes') {
    initPreferences(main.querySelector('#pfPrefs'), { path: userPath('settings') }).catch(() => {});
    initPush(main.querySelector('#pfPush')).catch(() => {}); // optional: never breaks the page
  }
}

function onTabKey(e) {
  const move = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
  if (!move) return;
  const tabs = [...main.querySelectorAll('.pf-tab')];
  const next = tabs[(tabs.indexOf(document.activeElement) + move + tabs.length) % tabs.length];
  showTab(next.dataset.tab);
  next.focus();
}

// Show another season (or the total) or, with no argument, refresh the one on screen after a change:
// only the numbers are redrawn, not the whole page.
async function refreshSummary(season = shown) {
  const data = await api(`${userPath('profile')}${season == null ? '' : `?season=${season}`}`);
  if (!data) return;
  const changed = data.season !== onScreen;
  shown = season;
  onScreen = data.season;
  mount(main.querySelector('#pfSeasons'), seasonPills(data));
  main.querySelector('#pfStats').setAttribute('aria-label', `Estadísticas: ${seasonName(data)}`);
  mount(main.querySelector('#pfStats'), statsView(data));
  mount(main.querySelector('#pfTopTitle'), titleView(`Más jugados ${seasonSuffix(data)}`));
  mount(main.querySelector('#pfTop'), topView(data));
  mount(main.querySelector('#pfAchTitle'), titleView(`Logros ${seasonSuffix(data)}`));
  mount(main.querySelector('#pfAchievements'), achievementsView(data));
  mount(main.querySelector('#pfGamesTitle'), titleView(`Juegos ${seasonSuffix(data)}`));
  if (changed && opened.has('resumen')) await showSeason(data.season);
}

async function onSeason(e) {
  const pill = e.target.closest('[data-season]');
  if (!pill || pill.getAttribute('aria-pressed') === 'true') return;
  const value = pill.dataset.season === seasons.ALL ? seasons.ALL : Number(pill.dataset.season);
  try {
    await refreshSummary(value);
  } catch (err) {
    flash(main.querySelector('#pfAvatarMsg'), err.message);
  }
}

// ── Templates ───────────────────────────────────────────────
const statTile = (label, value) => html`
  <div class="pf-stat"><div class="pf-stat-value">${value}</div><div class="pf-stat-label">${label}</div></div>`;

function avatar(d) {
  const initial = (d.user.name || d.user.username)[0].toUpperCase();
  return avatarUrl
    ? html`<img src="${avatarUrl}" alt="" class="pf-avatar" id="pfAvatar" />`
    : html`<div class="pf-avatar pf-avatar-placeholder" id="pfAvatar" aria-hidden="true">${initial}</div>`;
}

const titleView = (title) => html`<h2 class="section-title">${title}</h2><div class="section-line"></div>`;
const sectionTitle = (title, id) => html`<div class="section-header" ${id ? html`id="${id}"` : ''}>${titleView(title)}</div>`;

const seasonName = (d) => (d.season === seasons.ALL ? 'todas las temporadas' : `temporada ${d.season}`);
const seasonSuffix = (d) => (d.season === seasons.ALL ? '(total)' : `en ${d.season}`);

function seasonPills(d) {
  return html`${seasons.choices(d.seasons).map(({ value, label }) => html`
    <button type="button" class="pf-season-badge" data-season="${value}" aria-pressed="${String(value === d.season)}">${value === seasons.ALL ? label : `Temporada ${label}`}</button>`)}`;
}

function statsView(d) {
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

function topView(d) {
  const max = Math.max(1, ...d.top_games.map((g) => g.played_time));
  return d.top_games.length
    ? html`${d.top_games.map((g) => topGameRow(g, max))}`
    : html`<div class="pf-empty">Aún no hay tiempo registrado.</div>`;
}

function achievementsView(d) {
  return d.achievements.length
    ? html`${d.achievements.map((a) => html`<div class="pf-row"><div class="pf-row-main"><strong>${a.title}</strong></div><div class="pf-sub">${formatDate(a.date)}</div></div>`)}`
    : html`<div class="pf-empty">Todavía no has conseguido logros.</div>`;
}

function topGameRow(g, max) {
  const width = Math.max(3, Math.round((g.played_time / max) * 100));
  return html`
    <div class="pf-bar-row">
      <div class="pf-bar-label"><span>${g.game_name} ${scoreBadge(g.score)}</span><span>${formatDuration(g.played_time)}</span></div>
      <div class="pf-bar"><div style="width:${width}%"></div></div>
    </div>`;
}

function draw(d) {
  mount(main, html`
    <div class="pf-head">
      ${avatar(d)}
      <div class="pf-head-text">
        <h1 class="pf-title">${d.user.name || d.user.username}</h1>
        <div class="pf-sub">@${d.user.username}</div>
        <div class="pf-avatar-actions">
          <label class="pf-btn">Cambiar foto<input type="file" id="pfAvatarInput" accept="image/png,image/jpeg" hidden /></label>
          <span class="pf-msg" id="pfAvatarMsg" role="status"></span>
        </div>
      </div>
    </div>

    <div class="pf-season" id="pfSeasons" role="group" aria-label="Temporada">${seasonPills(d)}</div>
    <section class="pf-stats" id="pfStats" aria-label="Estadísticas: ${seasonName(d)}">${statsView(d)}</section>

    <nav class="pf-tabs" role="tablist" aria-label="Secciones del perfil">
      ${TABS.map(([id, label]) => html`<button class="pf-tab" role="tab" type="button" id="pfTab-${id}" aria-controls="pfPanel-${id}" data-tab="${id}">${label}</button>`)}
    </nav>

    <section class="pf-panel" role="tabpanel" id="pfPanel-resumen" aria-labelledby="pfTab-resumen">
      <div class="pf-cols">
        <div>
          ${sectionTitle(`Más jugados ${seasonSuffix(d)}`, 'pfTopTitle')}
          <div class="pf-card" id="pfTop">${topView(d)}</div>
        </div>
        <div>
          ${sectionTitle(`Logros ${seasonSuffix(d)}`, 'pfAchTitle')}
          <div class="pf-card" id="pfAchievements">${achievementsView(d)}</div>
        </div>
      </div>
      ${sectionTitle(`Juegos ${seasonSuffix(d)}`, 'pfGamesTitle')}
      <div id="pfLibrary"></div>
    </section>

    <section class="pf-panel" role="tabpanel" id="pfPanel-recomendados" aria-labelledby="pfTab-recomendados" hidden>
      <div class="pf-sub pf-note">Juegos que tienen los demás y tú nunca has jugado, empezando por los que más gente comparte.</div>
      <div id="pfRecommended"></div>
    </section>

    <section class="pf-panel" role="tabpanel" id="pfPanel-ajustes" aria-labelledby="pfTab-ajustes" hidden>
    <div class="pf-cols pf-cols-top">
    <div>
    ${sectionTitle('Mis datos')}
    <form class="pf-card pf-form" id="pfData" novalidate>
      <label>Usuario (apodo)<input class="adm-input" type="text" value="${d.user.username}" disabled /></label>
      <label>Nombre<input class="adm-input" type="text" name="name" value="${d.user.name || ''}" autocomplete="name" /></label>
      <label>Email (con el que inicias sesión)<input class="adm-input" type="email" name="email" value="${d.user.email || ''}" autocomplete="email" /></label>
      <label>Telegram ID<input class="adm-input" type="number" name="telegram_id" value="${d.user.telegram_id ?? ''}" /></label>
      <div class="pf-sub">Solo cámbialo si sabes lo que haces: es el número con el que el bot te reconoce y te escribe. Uno incorrecto puede dejarte sin avisos o enviárselos a otra persona.</div>
      <div class="pf-msg" id="pfDataMsg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Guardar datos</button></div>
    </form>

    <div id="pfPrefs"></div>

    <div id="pfPush"></div>

    </div>
    <div>
    ${sectionTitle('Cambiar contraseña')}
    <form class="pf-card pf-form" id="pfPass" novalidate>
      <label>Contraseña actual<input class="adm-input" type="password" name="current" autocomplete="current-password" /></label>
      <label>Nueva contraseña<input class="adm-input" type="password" name="next" autocomplete="new-password" /></label>
      <label>Repite la nueva contraseña<input class="adm-input" type="password" name="again" autocomplete="new-password" /></label>
      <div class="pf-sub">${PASSWORD_HINT}</div>
      <div class="pf-msg" id="pfPassMsg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Cambiar contraseña</button></div>
    </form>
    </div>
    </div>
    </section>`);

  main.querySelector('.pf-tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('.pf-tab');
    if (tab) showTab(tab.dataset.tab);
  });
  main.querySelector('.pf-tabs').addEventListener('keydown', onTabKey);
  main.querySelector('#pfSeasons').addEventListener('click', onSeason);
  initAvatar(main, { path: userPath('avatar') });
  initAccount(main, { user, userPath });
}
