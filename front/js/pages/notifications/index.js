// Notifications page (#/notifications): what the group and you were told, for whoever missed a push or has them off.
// GET /notifications; each notice is deleted on its own or all at once, and the API purges the old ones.
import { api } from '../../lib/api.js';
import { formatDateTime } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { setUnread } from '../../ui/layout.js';
import { toast } from '../../ui/toast.js';

export const active = 'notifications';

const ARM_MS = 4000; // the second click of "Vaciar" has to come within this time

let main;
let armTimer;

// A notice that opens a page is a link; one that only says "/" is plain text
const opens = (url) => url && url !== '/';

const card = (n) => {
  const content = html`
    <div class="nt-title">${n.title}</div>
    ${n.body ? html`<div class="nt-body">${n.body}</div>` : ''}
    <div class="nt-date">${formatDateTime(n.created_at)}</div>`;
  return html`
    <div class="gc-card nt-card ${n.read ? '' : 'unread'}">
      ${opens(n.url) ? html`<a class="nt-link" href="${n.url}">${content}</a>` : html`<div class="nt-link">${content}</div>`}
      <button class="nt-remove" type="button" data-remove="${n.id}" aria-label="Borrar el aviso" title="Borrar">×</button>
    </div>`;
};

function draw({ items }) {
  mount(main.querySelector('#ntList'), items.length
    ? html`<div class="nt-list">${items.map(card)}</div>`
    : html`<div class="pf-empty">No tienes avisos. Aquí aparecen los avisos del grupo y los tuyos, aunque tengas las notificaciones desactivadas.</div>`);
  main.querySelector('#ntClear').hidden = !items.length;
}

async function load() {
  try {
    const data = await api('/notifications/');
    if (!data) return;
    draw(data);
    // seeing them is reading them; the highlight stays until the next visit
    if (data.unread) {
      await api('/notifications/read', { method: 'POST' });
      setUnread(0);
    }
  } catch (err) {
    mount(main.querySelector('#ntList'), html`<div class="pf-empty">Error cargando los avisos: ${err.message}</div>`);
  }
}

async function remove(id) {
  try {
    await api(`/notifications/${encodeURIComponent(id)}`, { method: 'DELETE' });
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

async function clearAll(button) {
  if (!button.dataset.armed) {
    button.dataset.armed = '1';
    button.textContent = '¿Vaciar todo?';
    armTimer = setTimeout(() => disarm(button), ARM_MS);
    return;
  }
  disarm(button);
  try {
    await api('/notifications/', { method: 'DELETE' });
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

function disarm(button) {
  clearTimeout(armTimer);
  delete button.dataset.armed;
  button.textContent = 'Vaciar todo';
}

export async function render(ctx) {
  main = ctx.main;
  mount(main, html`
    <div class="wl-head">
      <h1 class="pf-title">Avisos</h1>
      <button class="pf-btn" type="button" id="ntClear" hidden>Vaciar todo</button>
    </div>
    <div id="ntList"><div class="loading-spinner">Cargando tus avisos...</div></div>`);
  main.querySelector('#ntClear').addEventListener('click', (e) => clearAll(e.currentTarget));
  main.querySelector('#ntList').addEventListener('click', (e) => {
    const button = e.target.closest('[data-remove]');
    if (button) remove(button.dataset.remove);
  });
  await load();
}

export function dispose() {
  clearTimeout(armTimer);
}
