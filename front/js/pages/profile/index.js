// Profile page: a header (photo and name) and, below it, the layout of the admin panel: a side menu
// (a collapsible bar on a phone) with two sections so nothing needs a long scroll. Resumen is the
// default: the stats of a season (the running one, another one or the total of all, chosen with the
// pills), top games, achievements and, below them, the games of the selected season (see library.js).
// Ajustes (personal data, password, notifications, session) is the other; it loads the first time it is opened.
// The layout classes (adm-shell, adm-side, adm-nav...) are the admin's, so both look the same.
// All routes are /api/v1/users/{username}/...
import { api } from '../../lib/api.js';
import { html, mount } from '../../lib/html.js';
import { PASSWORD_HINT } from '../../lib/password.js';
import * as seasons from '../../lib/seasons.js';
import { achievementsView, sectionTitle, seasonName, seasonPills, seasonSuffix, statsView, titleView, topView } from '../../ui/profile-summary.js';
import { initAbout } from './about.js';
import { initAccount } from './account.js';
import { initAvatar } from './avatar.js';
import { initData } from './data.js';
import { flash } from './flash.js';
import { initLibrary, showSeason } from './library.js';
import { initNotifications } from './notifications.js';
import { initPreferences } from './preferences.js';
import { initPush } from './push.js';

export const active = 'profile';
export const mainClass = 'profile-main';

// Off: the "Jugando ahora" preference is not offered in the profile. Its form (preferences.js), the API
// setting and the filter on the navbar chip stay, so turning this on brings the option back.
const SHOW_PLAYING_OPTION = false;

const TABS = [
  ['resumen', 'Resumen'],
  ['ajustes', 'Ajustes'],
];

let main;
let user;
let avatarUrl;
let opened; // tabs already initialised
let aboutYou; // the city and birth date inside "Mis datos" (about.js): saved with the rest of the form
let onLogout;
let shown; // season asked for: a year, or seasons.ALL; null = the running one
let onScreen; // season on screen once resolved: a year, or seasons.ALL

const userPath = (suffix) => `/users/${encodeURIComponent(user.username)}/${suffix}`;

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  avatarUrl = ctx.avatarUrl;
  onLogout = ctx.onLogout;
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
    if (on) main.querySelector('#pfNavCurrent').textContent = tab.textContent;
  });
  closeNav();
  main.querySelectorAll('.pf-panel').forEach((panel) => { panel.hidden = panel.id !== `pfPanel-${id}`; });
  history.replaceState(null, '', `#/profile/${id}`);
  if (opened.has(id)) return;
  opened.add(id);
  if (id === 'resumen') initLibrary(main.querySelector('#pfLibrary'), { username: user.username, userId: user.id, season: onScreen, onChange: refreshSummary });
  if (id === 'ajustes') {
    initNotifications(main.querySelector('#pfNotifs'), { path: userPath('settings') }).catch(() => {});
    if (SHOW_PLAYING_OPTION) initPreferences(main.querySelector('#pfPrefs'), { path: userPath('settings') }).catch(() => {});
    initPush(main.querySelector('#pfPush')).catch(() => {}); // optional: never breaks the page
    initAbout(main.querySelector('#pfAbout'), { path: userPath('settings') }).then((about) => { aboutYou = about; }).catch(() => {});
    initData(main.querySelector('#pfDataFiles'), { username: user.username });
  }
}

function closeNav() {
  main.querySelector('.adm-side').classList.remove('open');
  main.querySelector('#pfSideToggle').setAttribute('aria-expanded', 'false');
}

function onTabKey(e) {
  const move = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
  if (!move) return;
  e.preventDefault();
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
function avatar(d) {
  const initial = (d.user.name || d.user.username)[0].toUpperCase();
  return avatarUrl
    ? html`<img src="${avatarUrl}" alt="" class="pf-avatar" id="pfAvatar" />`
    : html`<div class="pf-avatar pf-avatar-placeholder" id="pfAvatar" aria-hidden="true">${initial}</div>`;
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

    <div class="adm-shell pf-shell">
    <aside class="adm-side">
      <button class="adm-side-toggle" type="button" id="pfSideToggle" aria-expanded="false" aria-controls="pfNav">
        <span class="adm-side-burger" aria-hidden="true"></span>
        <span class="adm-side-text"><strong id="pfNavCurrent"></strong></span>
        <span class="adm-side-caret" aria-hidden="true"></span>
      </button>
      <nav class="adm-nav pf-tabs" id="pfNav" role="tablist" aria-orientation="vertical" aria-label="Secciones del perfil">
        ${TABS.map(([id, label]) => html`<button class="adm-nav-item pf-tab" role="tab" type="button" id="pfTab-${id}" aria-controls="pfPanel-${id}" data-tab="${id}">${label}</button>`)}
      </nav>
    </aside>

    <div class="pf-content">
    <section class="pf-panel" role="tabpanel" id="pfPanel-resumen" aria-labelledby="pfTab-resumen">
      <div class="pf-season" id="pfSeasons" role="group" aria-label="Temporada">${seasonPills(d)}</div>
      <section class="pf-stats" id="pfStats" aria-label="Estadísticas: ${seasonName(d)}">${statsView(d)}</section>
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

    <section class="pf-panel" role="tabpanel" id="pfPanel-ajustes" aria-labelledby="pfTab-ajustes" hidden>
    ${sectionTitle('Mis datos')}
    <form class="pf-card pf-form" id="pfData" novalidate>
      <label>Usuario (apodo)<input class="adm-input" type="text" value="${d.user.username}" disabled /></label>
      <label>Nombre<input class="adm-input" type="text" name="name" value="${d.user.name || ''}" autocomplete="name" /></label>
      <label>Email (con el que inicias sesión)<input class="adm-input" type="email" name="email" value="${d.user.email || ''}" autocomplete="email" /></label>
      <label>Telegram ID<input class="adm-input" type="number" name="telegram_id" value="${d.user.telegram_id ?? ''}" /></label>
      <div class="pf-sub">Solo cámbialo si sabes lo que haces: es el número con el que el bot te reconoce y te escribe. Uno incorrecto puede dejarte sin avisos o enviárselos a otra persona.</div>
      <div id="pfAbout" class="pf-form"></div>
      <div class="pf-msg" id="pfDataMsg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Guardar datos</button></div>
    </form>

    ${sectionTitle('Cambiar contraseña')}
    <form class="pf-card pf-form" id="pfPass" novalidate>
      <label>Contraseña actual<input class="adm-input" type="password" name="current" autocomplete="current-password" /></label>
      <label>Nueva contraseña<input class="adm-input" type="password" name="next" autocomplete="new-password" /></label>
      <label>Repite la nueva contraseña<input class="adm-input" type="password" name="again" autocomplete="new-password" /></label>
      <div class="pf-sub">${PASSWORD_HINT}</div>
      <div class="pf-msg" id="pfPassMsg" role="status"></div>
      <div><button class="pf-btn primary" type="submit">Cambiar contraseña</button></div>
    </form>

    <div id="pfNotifs"></div>

    <div id="pfPush"></div>

    <div id="pfPrefs"></div>

    <div id="pfDataFiles"></div>

    ${sectionTitle('Sesión')}
    <div class="pf-card pf-form">
      <div class="pf-sub">Cierra la sesión en este dispositivo.</div>
      <div><button class="pf-btn danger" type="button" id="pfLogout">Cerrar sesión</button></div>
    </div>
    </section>
    </div>
    </div>`);

  main.querySelector('#pfSideToggle').addEventListener('click', (e) => {
    const open = main.querySelector('.adm-side').classList.toggle('open');
    e.currentTarget.setAttribute('aria-expanded', String(open));
  });
  main.querySelector('.pf-tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('.pf-tab');
    if (tab) showTab(tab.dataset.tab);
  });
  main.querySelector('.pf-tabs').addEventListener('keydown', onTabKey);
  main.querySelector('#pfSeasons').addEventListener('click', onSeason);
  main.querySelector('#pfLogout').addEventListener('click', () => onLogout());
  initAvatar(main, { path: userPath('avatar') });
  initAccount(main, { user, userPath, about: () => aboutYou });
}
