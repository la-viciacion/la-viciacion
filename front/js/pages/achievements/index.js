// Achievements page (#/achievements): the achievements the viewer has unlocked with their picture and description, and
// who of the group has unlocked them and when; the rest are listed hidden. GET /group/achievements (derived, nothing stored).
import { API_BASE, api } from '../../lib/api.js';
import { formatDate, formatPlayers } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { specialClass, specialTag } from '../../lib/special.js';

export const active = null; // it belongs to no item of the top bar

const picture = (a) => (a.has_image
  ? html`<img class="ach-img" src="${API_BASE}/utils/achievement-image/${a.key}" alt="" loading="lazy" />`
  : html`<div class="ach-img ach-img-placeholder" aria-hidden="true">🏆</div>`);

const who = (a) => {
  if (!a.unlocked_by) return html`<div class="pf-sub">Nadie lo ha conseguido todavía.</div>`;
  const names = a.players.map((p) => (p.times > 1 ? `${p.name} (×${p.times})` : p.name));
  return html`<div class="pf-sub">Lo han conseguido ${a.unlocked_by}: ${formatPlayers(names, 4)}. Último: ${formatDate(a.players[0].last)}</div>`;
};

// A secret one that the viewer has not unlocked says nothing: not even the name. A special one still has the aura
// of its level, so that everybody knows there are special ones to unlock.
const hiddenCard = (a) => html`
  <article class="ach-card hidden${specialClass(a.special)}">
    <div class="ach-head">
      <div class="ach-img ach-img-placeholder" aria-hidden="true">🔒</div>
      <div class="ach-title"><strong>Logro oculto</strong></div>
    </div>
    <div class="ach-body">
      <div class="pf-sub">Desbloquéalo para descubrirlo.</div>
    </div>
  </article>`;

// One the viewer has not unlocked (and is not secret) is shown dimmed, with its name only: what it is about is for
// them to work out.
const card = (a) => (a.hidden ? hiddenCard(a) : html`
  <article class="ach-card ${a.unlocked_by_me ? 'mine' : 'locked'}${specialClass(a.special)}">
    <div class="ach-head">
      ${picture(a)}
      <div class="ach-title"><strong>${a.title}</strong>${a.secret ? html`<span class="pf-tag secret">Secreto</span>` : ''}${specialTag(a.special)}${a.lifetime ? html`<span class="pf-tag muted">Único</span>` : ''}</div>
    </div>
    <div class="ach-body">
      ${a.description ? html`<div class="pf-sub">${a.description}</div>` : ''}
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
