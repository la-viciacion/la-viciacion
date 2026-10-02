// Modal dialogs. Anything inside the content marked [data-close] closes it.
import { html, mount, raw } from '../lib/html.js';

const openModals = new Set();

/** Standard header: title + close button. */
export const modalHeader = (title) => html`
  <div class="modal-header">
    <h3>${title}</h3>
    <button class="modal-close" data-close aria-label="Cerrar">${raw('&times;')}</button>
  </div>`;

/**
 * Open a modal with the given html`` content.
 * Returns { el, close }; onClose runs however the modal is dismissed
 * (close button, click outside, Escape or close()).
 */
export function openModal(content, { wide = false, onClose } = {}) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  mount(overlay, html`<div class="modal-content ${wide ? 'modal-wide' : ''}">${content}</div>`);

  const onKey = (e) => { if (e.key === 'Escape') close(); };
  function close() {
    if (!openModals.delete(close)) return;
    document.removeEventListener('keydown', onKey);
    overlay.remove();
    onClose?.();
  }

  overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });
  overlay.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) close(); });
  document.addEventListener('keydown', onKey);
  document.body.appendChild(overlay);
  openModals.add(close);
  return { el: overlay, close };
}

export function closeAllModals() {
  [...openModals].forEach((close) => close());
}
