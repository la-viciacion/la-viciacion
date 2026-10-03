// Achievements page (#/achievements): every achievement with its picture and description, and who of the group has
// unlocked it and when. GET /group/achievements (derived, nothing stored).
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

const card = (a) => html`
  <article class="ach-card ${a.unlocked_by_me ? 'mine' : ''}">
    ${picture(a)}
    <div class="ach-body">
      <div class="ach-title"><strong>${a.title}</strong>${a.unlocked_by_me ? html`<span class="pf-tag done">Lo tienes</span>` : ''}</div>
      <div class="pf-sub">${a.description}</div>
      ${who(a)}
    </div>
  </article>`;

export async function render({ main }) {
  mount(main, html`
    <div class="section-header"><h2 class="section-title">Logros</h2><div class="section-line"></div></div>
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
