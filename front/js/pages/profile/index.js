// Profile page: a header with the season stats and three tabs so nothing needs a
// long scroll: Resumen (top games, achievements), Mis juegos (see library.js) and
// Ajustes (personal data, reminders, push notifications, password). The games and the
// settings load the first time their tab is opened.
// All routes are /api/v1/users/{username}/...
import { api, jsonRequest } from '../../lib/api.js';
import { formatDate, formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { PASSWORD_HINT, isValidPassword } from '../../lib/password.js';
import { initLibrary } from './library.js';
import { initPreferences } from './preferences.js';
import { initPush } from './push.js';

export const active = 'profile';
export const mainClass = 'profile-main';

const AVATAR_SIZE = 256;

const TABS = [
  ['resumen', 'Resumen'],
  ['juegos', 'Mis juegos'],
  ['ajustes', 'Ajustes'],
];

let main;
let user;
let avatarUrl;
let opened; // tabs already initialised

const userPath = (suffix) => `/users/${encodeURIComponent(user.username)}/${suffix}`;

function flash(el, message, ok = false) {
  el.textContent = message;
  el.className = `pf-msg ${message ? (ok ? 'ok' : 'err') : ''}`;
}

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  avatarUrl = ctx.avatarUrl;
  await load();
}

async function load() {
  const data = await api(userPath('profile'));
  if (!data) return;
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
  if (id === 'juegos') initLibrary(main.querySelector('#pfLibrary'), { username: user.username, onChange: refreshSummary });
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

// A completion changed: refresh the numbers without redrawing the whole page.
async function refreshSummary() {
  const data = await api(userPath('profile'));
  if (!data) return;
  mount(main.querySelector('#pfStats'), statsView(data));
  mount(main.querySelector('#pfTop'), topView(data));
  mount(main.querySelector('#pfAchievements'), achievementsView(data));
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

const sectionTitle = (title) => html`<div class="section-header"><h2 class="section-title">${title}</h2><div class="section-line"></div></div>`;

function statsView(d) {
  const s = d.stats;
  return html`
    ${statTile('Tiempo jugado', formatDuration(s.played_time))}
    ${statTile('Días jugados', s.played_days)}
    ${statTile('Juegos jugados', s.played_games)}
    ${statTile('Completados', s.completed_games)}
    ${statTile('Racha actual', `${s.current_streak} d`)}
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
      <div class="pf-bar-label"><span>${g.game_name}</span><span>${formatDuration(g.played_time)}</span></div>
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

    <div class="pf-season">
      <span class="pf-season-badge">Temporada ${d.season}</span>
    </div>
    <section class="pf-stats" id="pfStats" aria-label="Estadísticas de la temporada ${d.season}">${statsView(d)}</section>

    <nav class="pf-tabs" role="tablist" aria-label="Secciones del perfil">
      ${TABS.map(([id, label]) => html`<button class="pf-tab" role="tab" type="button" id="pfTab-${id}" aria-controls="pfPanel-${id}" data-tab="${id}">${label}</button>`)}
    </nav>

    <section class="pf-panel" role="tabpanel" id="pfPanel-resumen" aria-labelledby="pfTab-resumen">
      <div class="pf-cols">
        <div>
          ${sectionTitle(`Más jugados en ${d.season}`)}
          <div class="pf-card" id="pfTop">${topView(d)}</div>
        </div>
        <div>
          ${sectionTitle(`Logros de ${d.season}`)}
          <div class="pf-card" id="pfAchievements">${achievementsView(d)}</div>
        </div>
      </div>
    </section>

    <section class="pf-panel" role="tabpanel" id="pfPanel-juegos" aria-labelledby="pfTab-juegos" hidden>
      <div class="pf-sub pf-note">Aquí aparecen los juegos de todas las temporadas; la temporada de cada uno va indicada.</div>
      <div id="pfLibrary"></div>
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
  main.querySelector('#pfAvatarInput').addEventListener('change', changeAvatar);
  main.querySelector('#pfData').addEventListener('submit', saveData);
  main.querySelector('#pfPass').addEventListener('submit', changePassword);
}

// ── Avatar ──────────────────────────────────────────────────
// Center-crop to a square and shrink, so the stored avatar stays small.
function resizeImage(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const src = URL.createObjectURL(file);
    img.onload = () => {
      const side = Math.min(img.width, img.height);
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = AVATAR_SIZE;
      canvas.getContext('2d').drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, AVATAR_SIZE, AVATAR_SIZE);
      URL.revokeObjectURL(src);
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('No se pudo procesar la imagen'))), 'image/jpeg', 0.9);
    };
    img.onerror = () => { URL.revokeObjectURL(src); reject(new Error('El archivo no es una imagen válida')); };
    img.src = src;
  });
}

// Swap a placeholder (or old image) for the new picture, keeping its classes.
function showAvatar(el) {
  if (!el) return;
  const img = document.createElement('img');
  img.src = avatarUrl;
  img.alt = '';
  img.className = el.className.replace(/\s*(navbar|pf)-avatar-placeholder/, '').trim();
  if (el.id) img.id = el.id;
  el.replaceWith(img);
}

async function changeAvatar(e) {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  const msg = main.querySelector('#pfAvatarMsg');
  if (!['image/jpeg', 'image/png'].includes(file.type)) return flash(msg, 'Solo se admiten imágenes JPG o PNG');
  flash(msg, 'Subiendo…', true);
  try {
    const small = await resizeImage(file);
    const form = new FormData();
    form.append('file', small, 'avatar.jpg');
    await api(userPath('avatar'), { method: 'PATCH', body: form });
    avatarUrl = URL.createObjectURL(small);
    showAvatar(main.querySelector('#pfAvatar'));
    showAvatar(document.querySelector('.navbar-avatar'));
    flash(msg, 'Foto actualizada', true);
  } catch (err) {
    flash(msg, err.message);
  }
}

// ── Personal data & password ────────────────────────────────
async function saveData(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const msg = main.querySelector('#pfDataMsg');
  // The email identifies the account, so it is only sent when filled in.
  const telegram = form.telegram_id.value.trim();
  const changes = { name: form.name.value, telegram_id: telegram === '' ? null : Number(telegram) };
  if (form.email.value.trim()) changes.email = form.email.value;
  try {
    const updated = await api(userPath('profile'), jsonRequest('PATCH', changes));
    Object.assign(user, { name: updated.name, email: updated.email, telegram_id: updated.telegram_id });
    const shown = updated.name || updated.username;
    main.querySelector('.pf-title').textContent = shown;
    const navName = document.querySelector('.navbar-username');
    if (navName) navName.textContent = shown;
    flash(msg, 'Datos guardados', true);
  } catch (err) {
    flash(msg, err.message);
  }
}

async function changePassword(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const msg = main.querySelector('#pfPassMsg');
  if (!form.current.value) return flash(msg, 'Introduce tu contraseña actual');
  if (!isValidPassword(form.next.value)) return flash(msg, `La contraseña debe tener ${PASSWORD_HINT.toLowerCase()}`);
  if (form.next.value !== form.again.value) return flash(msg, 'Las contraseñas nuevas no coinciden');
  try {
    await api(userPath('password'), jsonRequest('POST', {
      current_password: form.current.value,
      new_password: form.next.value,
    }));
    form.reset();
    flash(msg, 'Contraseña actualizada', true);
  } catch (err) {
    flash(msg, err.message);
  }
}
