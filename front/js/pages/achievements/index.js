// Achievements page (#/achievements): the achievements the viewer has unlocked with their picture and description, and
// who of the group has unlocked them and when; the rest are listed hidden. GET /group/achievements (derived, nothing stored).
import { API_BASE, api } from '../../lib/api.js';
import { formatDate, formatPlayers } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';

export const active = null; // it belongs to no item of the top bar

const picture = (a) => (a.has_image
  ? html`<img class="ach-img" src="${API_BASE}/utils/achievement-image/${a.key}" alt="" loading="lazy" />`
  : html`<div class="ach-img ach-img-placeholder" aria-hidden="true">🏆</div>`);

const who = (a) => {
  if (!a.unlocked_by) return html`<div class="pf-sub">Nadie lo ha conseguido todavía.</div>`;
  const names = a.players.map((p) => (p.times > 1 ? `${p.name} (×${p.times})` : p.name));
  return html`<div class="pf-sub">Lo han conseguido ${a.unlocked_by}: ${formatPlayers(names, 4)}. Último: ${formatDate(a.players[0].last)}</div>`;
};

// What the viewer has not unlocked says nothing: not even the name. A secret one still has its golden aura, so
// that everybody knows there are special ones to unlock.
const hiddenCard = (a) => html`
  <article class="ach-card hidden${a.secret ? ' secret' : ''}">
    <div class="ach-img ach-img-placeholder" aria-hidden="true">🔒</div>
    <div class="ach-body">
      <div class="ach-title"><strong>Logro oculto</strong></div>
      <div class="pf-sub">Desbloquéalo para descubrirlo.</div>
    </div>
  </article>`;

// A secret one has a golden aura: it was announced to the group without saying which.
const card = (a) => (a.hidden ? hiddenCard(a) : html`
  <article class="ach-card mine${a.secret ? ' secret' : ''}">
    ${picture(a)}
    <div class="ach-body">
      <div class="ach-title"><strong>${a.title}</strong><span class="pf-tag done">Lo tienes</span>${a.secret ? html`<span class="pf-tag secret">Secreto</span>` : ''}</div>
      <div class="pf-sub">${a.description}</div>
      ${who(a)}
    </div>
  </article>`);

export async function render({ main }) {
  mount(main, html`
    <h1 class="pf-title pg-title">Logros</h1>
    <div id="achList"><div class="loading-spinner">Cargando logros...</div></div>`);
  try {
    const list = await api('/group/achievements');
    if (!list) return;
    const mine = list.filter((a) => a.unlocked_by_me).length;
    mount(main.querySelector('#achList'), html`
      <div class="pf-sub ach-count" role="status">Tienes ${mine} de ${list.length}</div>
      <div class="ach-grid">${list.map(card)}</div>`);
  } catch (err) {
    mount(main.querySelector('#achList'), html`<div class="pf-empty">Error cargando los logros: ${err.message}</div>`);
  }
}
