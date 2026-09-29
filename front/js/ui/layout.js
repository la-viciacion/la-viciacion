// Page shell shared by every logged-in page: navbar + <main>.
import { html, mount } from '../lib/html.js';
import { iconLogout } from './icons.js';

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
        <img src="icon-64.png" alt="" class="navbar-logo" aria-hidden="true" />
        La Viciación
      </a>
      <div class="navbar-actions">
        ${link('#', 'home', 'Inicio')}
        ${user.is_admin ? link('#/admin', 'admin', 'Admin') : ''}
        <a href="#/profile" class="navbar-user ${active === 'profile' ? 'active' : ''}" title="Mi perfil (@${user.username})">
          ${avatarUrl
            ? html`<img src="${avatarUrl}" alt="" class="navbar-avatar" />`
            : html`<div class="navbar-avatar navbar-avatar-placeholder" aria-hidden="true">${initial}</div>`}
          <span class="navbar-username">${user.name || user.username}</span>
        </a>
        <button class="btn-logout" id="logoutBtn" aria-label="Cerrar sesión">${iconLogout()} Salir</button>
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
  return app().querySelector('main');
}
