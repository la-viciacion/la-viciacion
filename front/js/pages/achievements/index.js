// Achievements page (#/achievements): the achievements the viewer has unlocked with their picture and description, and
// who of the group has unlocked them and when; the rest are listed hidden. They come in two blocks, the ones earned
// once a season and the lifetime ones (earned once, counting the whole history). The ones that add something up show
// how far the viewer is from them. The season block has a pill per season: each shows only the achievements of that
// season, with who had them and whether the viewer did then. GET /group/achievements (derived, nothing stored).
import { API_BASE, api } from '../../lib/api.js';
import { formatDate, formatPlayers } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import * as seasons from '../../lib/seasons.js';
import { specialClass } from '../../lib/special.js';
import { iconChevron } from '../../ui/icons.js';
import { titleView } from '../../ui/profile-summary.js';

export const active = null; // it belongs to no item of the top bar

const picture = (a) => (a.has_image
  ? html`<img class="ach-img" src="${API_BASE}/utils/achievement-image/${a.key}" alt="" loading="lazy" />`
  : html`<div class="ach-img ach-img-placeholder" aria-hidden="true">🏆</div>`);

const who = (a) => {
  if (!a.unlocked_by) return html`<div class="pf-sub">Nadie lo ha conseguido todavía.</div>`;
  const names = a.players.map((p) => (p.times > 1 ? `${p.name} (×${p.times})` : p.name));
  return html`<div class="pf-sub">Lo han conseguido ${a.unlocked_by}: ${formatPlayers(names, 4)}. Último: ${formatDate(a.players[0].last)}</div>`;
};

// A secret one that the viewer has not unlocked says nothing: not even the name, only who has it (so that it is seen
// to be possible). A special one still has the aura of its level, so that everybody knows there are special ones to unlock.
const hiddenWho = (a) => (a.unlocked_by
  ? html`<div class="pf-sub">Lo han conseguido ${a.unlocked_by}: ${formatPlayers(a.players.map((p) => p.name), 4)}</div>`
  : html`<div class="pf-sub">Nadie lo ha conseguido todavía.</div>`);

const hiddenCard = (a) => html`
  <article class="ach-card hidden${specialClass(a.special)}">
    <div class="ach-head">
      <div class="ach-img ach-img-placeholder" aria-hidden="true">🔒</div>
      <div class="ach-title"><strong>Logro oculto</strong></div>
    </div>
    <div class="ach-body">
      <div class="pf-sub">Desbloquéalo para descubrirlo.</div>
      ${hiddenWho(a)}
    </div>
  </article>`;

// How far the viewer is from an achievement that adds something up: only a bar, with no count, goal or unit, so that
// a locked one does not say what it counts or where the limit is.
const progressBar = (p) => (p ? html`
  <div class="ach-progress">
    <div class="ach-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${p.percent}" aria-label="Progreso">
      <div class="ach-bar-fill" style="width: ${p.percent}%"></div>
    </div>
  </div>` : '');

// One the viewer has not unlocked (and is not secret) is shown dimmed, with its name only: what it is about is for
// them to work out.
const card = (a) => (a.hidden ? hiddenCard(a) : html`
  <article class="ach-card ${a.unlocked_by_me ? 'mine' : 'locked'}${specialClass(a.special)}">
    <div class="ach-head">
      ${picture(a)}
      <div class="ach-title"><strong>${a.title}</strong>${a.secret ? html`<span class="pf-tag secret">Secreto</span>` : ''}</div>
    </div>
    <div class="ach-body">
      ${a.description ? html`<div class="pf-sub">${a.description}</div>` : ''}
      ${progressBar(a.progress)}
      ${who(a)}
    </div>
  </article>`);

const BLOCKS = [
  { title: 'De temporada', note: 'Se consiguen una vez por temporada y cuentan solo lo jugado en ella.', pick: (a) => !a.lifetime, seasonal: true },
  { title: 'Lifetime', note: 'Cuentan todo tu historial y se consiguen una sola vez.', pick: (a) => a.lifetime },
];

let shown = seasons.current(); // the season on screen in the season block
const folded = new Set(); // the titles of the blocks the viewer has folded: they start open, and stay as left when a season changes

const pills = () => html`
  <div class="pf-season ach-seasons" role="group" aria-label="Temporada">${seasons.available().map((year) => html`
    <button type="button" class="pf-season-badge" data-season="${year}" aria-pressed="${String(year === shown)}">Temporada ${year}</button>`)}
  </div>`;

const block = ({ title, note, seasonal }, list) => html`
  <section class="ach-block ${folded.has(title) ? 'folded' : ''}">
    <button type="button" class="section-header ach-fold" data-fold="${title}" aria-expanded="${String(!folded.has(title))}">
      ${titleView(title)}<span class="ach-chevron" aria-hidden="true">${iconChevron()}</span>
    </button>
    <div class="ach-content">
      <div class="pf-sub ach-note">${note} Tienes ${list.filter((a) => a.unlocked_by_me).length} de ${list.length}.</div>
      ${seasonal ? pills() : ''}
      <div class="ach-grid">${list.map(card)}</div>
    </div>
  </section>`;

// The season block always shows (with its pills), even when the season has nothing: another one may have.
async function load(main) {
  const target = main.querySelector('#achList');
  try {
    const list = await api(shown === seasons.current() ? '/group/achievements' : `/group/achievements?season=${shown}`);
    if (!list) return;
    const mine = list.filter((a) => a.unlocked_by_me).length;
    mount(target, html`
      <div class="pf-sub ach-count" role="status">Tienes ${mine} de ${list.length}</div>
      ${BLOCKS.map((b) => ({ b, items: list.filter(b.pick) })).filter(({ b, items }) => items.length || b.seasonal).map(({ b, items }) => block(b, items))}`);
  } catch (err) {
    mount(target, html`<div class="pf-empty">Error cargando los logros: ${err.message}</div>`);
  }
}

export async function render({ main }) {
  shown = seasons.current();
  folded.clear();
  mount(main, html`
    <h1 class="pf-title pg-title">Logros</h1>
    <div id="achList"><div class="loading-spinner">Cargando logros...</div></div>`);
  main.querySelector('#achList').addEventListener('click', (e) => {
    const fold = e.target.closest('[data-fold]');
    if (fold) {
      const title = fold.dataset.fold;
      if (!folded.delete(title)) folded.add(title);
      fold.closest('.ach-block').classList.toggle('folded', folded.has(title));
      fold.setAttribute('aria-expanded', String(!folded.has(title)));
      return;
    }
    const pill = e.target.closest('[data-season]');
    if (!pill || pill.getAttribute('aria-pressed') === 'true') return;
    shown = Number(pill.dataset.season);
    load(main);
  });
  await load(main);
}
