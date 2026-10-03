// Page shell shared by every logged-in page: navbar + <main>.
import { html, mount } from '../lib/html.js';
import { startPresence } from '../lib/presence.js';
import { iconLogout } from './icons.js';
import { mountPlaying } from './playing.js';

const app = () => document.getElementById('app');

/** Full-screen spinner while a page loads. */
export function showLoading() {
  mount(app(), html`<div id="loading-overlay"><div class="spinner"></div></div>`);
}

function navbar(user, avatarUrl, active) {
  const initial = (user.name?.[0] || user.username[0]).toUpperCase();
  const link = (href, id, label) => html`<a href="${href}" class="navbar-link ${active === id ? 'active' : ''}">${label}</a>`;
  return html`
    <nav class="navbar" role="navigation" aria-label="Navegación principal">
      <a href="#" class="navbar-brand" aria-label="La Viciación inicio">
        <img src="assets/icons/icon-64.png" alt="" class="navbar-logo" aria-hidden="true" />
        La Viciación
      </a>
      <div class="navbar-actions">
        <div class="playing-slot" id="playingSlot"></div>
        ${link('#', 'home', 'Inicio')}
        ${user.is_admin ? link('#/admin', 'admin', 'Admin') : ''}
        <a href="#/profile" class="navbar-user ${active === 'profile' ? 'active' : ''}" title="Mi perfil (@${user.username})">
          ${avatarUrl
            ? html`<img src="${avatarUrl}" alt="" class="navbar-avatar" />`
            : html`<div class="navbar-avatar navbar-avatar-placeholder" aria-hidden="true">${initial}</div>`}
          <span class="navbar-username">${user.name || user.username}</span>
        </a>
        <button class="btn-logout" id="logoutBtn" type="button" aria-label="Cerrar sesión" title="Cerrar sesión">${iconLogout()}</button>
      </div>
    </nav>`;
}

/**
 * Render navbar + main and return the <main> element.
 * `mainClass` adds a page-specific modifier (e.g. "admin-main").
 */
export function renderShell({ user, avatarUrl, active, mainClass = '', onLogout }) {
  mount(app(), html`
    <div class="home-page">
      ${navbar(user, avatarUrl, active)}
      <main class="home-main ${mainClass}"></main>
    </div>`);
  document.getElementById('logoutBtn').addEventListener('click', onLogout);
  mountPlaying(document.getElementById('playingSlot'), user);
  startPresence();
  return app().querySelector('main');
}
