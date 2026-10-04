// The side menu: a button in the top bar that slides a panel in from the left. It closes with Escape, a tap
// outside or after choosing a page; the page it is on is highlighted. What is in it: lib/menu.js.
import { activeItem, menuSections } from '../lib/menu.js';
import { html, mount } from '../lib/html.js';
import { loadVersion } from '../lib/version.js';
import * as icons from './icons.js';

let open = null; // the close function of the menu that is on screen

const item = (it, current) => html`
  <a class="menu-item ${current === it.id ? 'active' : ''}" href="${it.href}" ${current === it.id ? html`aria-current="page"` : ''}>
    ${icons[it.icon]()}<span>${it.label}</span>${it.wip ? html`<span class="menu-wip">WIP</span>` : ''}
  </a>`;

function openMenu(button, { user, onLogout }) {
  if (open) return open();
  const current = activeItem(location.hash);
  const overlay = document.createElement('div');
  overlay.className = 'menu-overlay';
  mount(overlay, html`
    <aside class="menu-panel" id="menuPanel" role="dialog" aria-modal="true" aria-label="Menú">
      <div class="menu-head"><strong>La Viciación</strong>
        <button class="menu-close" type="button" data-close aria-label="Cerrar el menú">${icons.iconClose()}</button>
      </div>
      <nav class="menu-nav" aria-label="Secciones">
        ${menuSections(user).map((section) => html`
          <div class="menu-section">${section.label}</div>
          ${section.items.map((it) => item(it, current))}`)}
      </nav>
      <div class="menu-foot"><button class="menu-item menu-logout" type="button" id="menuLogout">${icons.iconLogout()}<span>Cerrar sesión</span></button>
        <small class="menu-version" id="menuVersion" hidden></small>
      </div>
    </aside>`);

  function close() {
    if (open !== close) return;
    open = null;
    document.removeEventListener('keydown', onKey);
    overlay.remove();
    button.setAttribute('aria-expanded', 'false');
    button.focus();
  }
  const onKey = (e) => { if (e.key === 'Escape') close(); };

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay || e.target.closest('[data-close]') || e.target.closest('a.menu-item')) close();
  });
  overlay.querySelector('#menuLogout').addEventListener('click', () => { close(); onLogout(); });
  loadVersion().then((version) => {
    const label = overlay.querySelector('#menuVersion');
    if (!version || !label) return;
    label.textContent = `v${version}`;
    label.hidden = false;
  });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(overlay);
  button.setAttribute('aria-expanded', 'true');
  open = close;
  (overlay.querySelector('a.menu-item.active') ?? overlay.querySelector('a.menu-item')).focus();
  return close;
}

/** Wires the menu button of the top bar. */
export function mountMenu(button, options) {
  button.addEventListener('click', () => openMenu(button, options));
}

/** Closes the menu if it is open (a page is leaving, or the session ends). */
export const closeMenu = () => open?.();
