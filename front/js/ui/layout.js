// Page shell shared by every logged-in page: navbar + <main>.
import { html, mount } from '../lib/html.js';
import { startPresence } from '../lib/presence.js';
import { iconHome, iconMenu, iconShield } from './icons.js';
import { mountMenu } from './menu.js';
import { mountPlaying } from './playing.js';

const app = () => document.getElementById('app');

/** Full-screen spinner while a page loads. */
export function showLoading() {
  mount(app(), html`<div id="loading-overlay"><div class="spinner"></div></div>`);
}

function navbar(user, avatarUrl, active) {
  const initial = (user.name?.[0] || user.username[0]).toUpperCase();
  // an icon on a phone, the icon and the word on a wide screen; the label is always there for screen readers
  const link = (href, id, label, icon) => html`<a href="${href}" class="navbar-link ${active === id ? 'active' : ''}" aria-label="${label}" title="${label}">${icon}<span class="navbar-link-text">${label}</span></a>`;
  return html`
    <nav class="navbar" role="navigation" aria-label="Navegación principal">
      <div class="navbar-left">
        <button class="menu-btn" id="menuBtn" type="button" aria-label="Abrir el menú" aria-haspopup="dialog" aria-expanded="false" aria-controls="menuPanel">${iconMenu()}</button>
        <a href="#" class="navbar-brand" aria-label="La Viciación inicio">
          <img src="assets/icons/icon-64.png" alt="" class="navbar-logo" aria-hidden="true" />
          La Viciación
        </a>
      </div>
      <div class="navbar-actions">
        <div class="playing-slot" id="playingSlot"></div>
        ${link('#', 'home', 'Inicio', iconHome())}
        <a href="#/profile" class="navbar-user ${active === 'profile' ? 'active' : ''}" title="Mi perfil (@${user.username})">
          ${avatarUrl
            ? html`<img src="${avatarUrl}" alt="" class="navbar-avatar" />`
            : html`<div class="navbar-avatar navbar-avatar-placeholder" aria-hidden="true">${initial}</div>`}
          <span class="navbar-username">${user.name || user.username}</span>
        </a>
        ${user.is_admin ? link('#/admin', 'admin', 'Panel de administración', iconShield()) : ''}
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
  mountMenu(document.getElementById('menuBtn'), { user, onLogout });
  mountPlaying(document.getElementById('playingSlot'), user);
  startPresence();
  return app().querySelector('main');
}
