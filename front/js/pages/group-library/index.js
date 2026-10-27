// Group library page (#/library): the libraries of the whole group at once. Hidden gems (few have them, those who rated
// them like them), the graveyard (games players gave up), rarities (games only one player has), what nobody has touched
// and what the libraries cover by genre and platform. GET /group/library; derived, nothing is stored.
// A row of pills at the top reaches every section at once (it unfolds the section and scrolls to it), and each section
// folds on its own; what the viewer folded is remembered in this browser.
import { api } from '../../lib/api.js';
import { formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { perHour } from '../../lib/money.js';
import { iconChevron } from '../../ui/icons.js';
import { scoreBadge } from '../../ui/score-badge.js';

export const active = 'library';

let main;
let data;
let value = null; // the group's cost per hour (GET /group/value), or null when it could not be loaded
const FOLDED_KEY = 'gl-folded';
let folded = new Set(); // the keys of the sections the viewer has folded: they start open

// Per-viewer convenience only: a browser that refuses storage just forgets.
function loadFolded() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FOLDED_KEY) || '[]'));
  } catch {
    return new Set();
  }
}

function saveFolded() {
  try {
    localStorage.setItem(FOLDED_KEY, JSON.stringify([...folded]));
  } catch {
    // nothing to do: it is not remembered
  }
}

const tile = (label, value) => html`<div class="pf-stat"><div class="pf-stat-value">${value}</div><div class="pf-stat-label">${label}</div></div>`;

const cover = (g) => (g.image_url
  ? html`<img src="${g.image_url}" alt="" class="pf-thumb" loading="lazy" />`
  : html`<div class="pf-thumb pf-thumb-placeholder" aria-hidden="true">🎮</div>`);

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/** A list of games: cover, name linking to its page and a line saying why it is there. */
function gameList(items, detail, empty) {
  if (!items.length) return html`<div class="pf-empty">${empty}</div>`;
  return html`<ul class="gl-games">${items.map((g) => html`
    <li class="gl-game">${cover(g)}
      <div><a class="game-link" href="${gameHref(g.game_id)}">${g.game_name}</a><div class="pf-sub">${detail(g)}</div></div></li>`)}</ul>`;
}

/** Horizontal bars for a coverage table: `label(row)` is the name and `amount(row)` the number the bar shows. */
function bars(rows, label, amount, extra) {
  const max = Math.max(1, ...rows.map(amount));
  return html`<div class="gl-bars">${rows.map((r) => html`
    <div class="gl-bar-row"><span class="gl-bar-name">${label(r)}</span>
      <span class="gl-bar"><i style="width:${Math.round((100 * amount(r)) / max)}%"></i></span>
      <span class="pf-sub">${plural(amount(r), 'juego', 'juegos')}${extra(r)}</span></div>`)}</div>`;
}

// A section that folds: a header that is a button, with how many items it has, and its body.
const section = (key, title, count, body, note = '') => html`
  <section class="ach-block gl-section ${folded.has(key) ? 'folded' : ''}" id="gl-${key}" data-section="${key}">
    <button type="button" class="section-header ach-fold" data-fold="${key}" aria-expanded="${String(!folded.has(key))}">
      <h2 class="section-title">${title}</h2><span class="pf-sub gl-count">${count}</span><div class="section-line"></div><span class="ach-chevron" aria-hidden="true">${iconChevron()}</span>
    </button>
    <div class="ach-content">
      ${note ? html`<p class="pf-sub gl-note">${note}</p>` : ''}
      <div class="pf-card">${body}</div>
    </div>
  </section>`;

/** The sections, in order: [key, title, how many items it has]. */
const sectionsOf = (d) => [
  ['gems', 'Joyas ocultas', d.hidden_gems.length],
  ['graveyard', 'El cementerio', d.graveyard.length],
  ['rarities', 'Rarezas', d.rarities.total],
  ['untouched', 'Sin tocar', d.untouched.total],
  ['genres', 'Por género', d.genres.length],
  ['platforms', 'Por plataforma', d.platforms.length],
  ...(value ? [['value', 'Rentabilidad', value.games]] : []),
];

/** The cheapest and the dearest per hour of the group (never a player, never a price): `value` is GET /group/value. */
function valueView(v) {
  if (!v.games) return html`<div class="pf-empty">Todavía ningún juego tiene precio de ${v.min_contributors} jugadores o más.</div>`;
  const list = (title, games) => html`
    <div class="pv-list"><h3>${title}</h3>
      ${games.map((g) => html`<div class="pv-item"><a class="game-link" href="${gameHref(g.game_id)}">${g.game_name}</a>
        <div class="pf-sub">${perHour(g.per_hour_cents)} · ${plural(g.contributors, 'jugador', 'jugadores')}</div></div>`)}
    </div>`;
  return html`<div class="pv-lists">${list('Más baratos por hora', v.cheapest)}${v.games > v.cheapest.length ? list('Más caros por hora', v.priciest) : ''}</div>`;
}

const more = (total, shown) => (total > shown ? html`<div class="pf-sub">y ${total - shown} más</div>` : '');

function draw(d) {
  const { summary } = d;
  const count = Object.fromEntries(sectionsOf(d).map(([key, , n]) => [key, n]));
  mount(main, html`
    <div class="wl-head"><h1 class="pf-title">Biblioteca del grupo</h1></div>
    <p class="pf-sub cal-intro">Las bibliotecas de todos juntas: lo que casi nadie conoce, lo que se abandona y lo que nadie ha tocado.</p>
    <section class="pf-stats" aria-label="La biblioteca del grupo">
      ${tile('Juegos distintos', summary.games)}
      ${tile('Jugadores', summary.players)}
      ${tile('Horas jugadas', formatDuration(summary.played_seconds))}
    </section>

    <nav class="pf-season gl-pills" aria-label="Secciones">
      ${sectionsOf(d).map(([key, title, n]) => html`<button type="button" class="pf-season-badge" data-go="${key}">${title} <span class="gl-count">${n}</span></button>`)}
    </nav>

    ${section('gems', 'Joyas ocultas', count.gems, gameList(d.hidden_gems, (g) => html`${plural(g.players, 'jugador lo tiene', 'jugadores lo tienen')} · nota media ${scoreBadge(Math.round(g.score_mean))} (${g.score_count})`, 'Todavía no hay ningún juego poco conocido y bien puntuado.'),
      'Juegos que tienen como mucho dos jugadores y a los que han dado una nota media de 80 o más.')}

    ${section('graveyard', 'El cementerio', count.graveyard, gameList(d.graveyard, (g) => `Abandonado por ${g.abandoned_by.join(', ')} · lo tienen ${g.players}`, 'Nadie ha abandonado nada. Qué constancia.'),
      'Juegos que alguien ha dado por perdidos y no ha vuelto a tocar.')}

    ${section('rarities', 'Rarezas', count.rarities, html`
      ${gameList(d.rarities.items, (g) => `Solo lo tiene ${g.owner}${g.seconds ? ` · ${formatDuration(g.seconds)}` : ' · sin jugar'}`, 'Todos los juegos los tiene más de una persona.')}
      ${more(d.rarities.total, d.rarities.items.length)}`,
      'Juegos que solo tiene una persona del grupo, los más jugados primero.')}

    ${section('untouched', 'Sin tocar', count.untouched, html`
      ${gameList(d.untouched.items, (g) => `${plural(g.players, 'jugador lo tiene', 'jugadores lo tienen')} y nadie lo ha jugado`, 'Todos los juegos de la biblioteca se han jugado alguna vez.')}
      ${more(d.untouched.total, d.untouched.items.length)}`,
      'Juegos que alguien tiene y que nadie ha llegado a jugar.')}

    <div class="pf-cols">
      <div>${section('genres', 'Por género', count.genres, d.genres.length ? bars(d.genres, (r) => r.genre, (r) => r.games, (r) => ` · ${formatDuration(r.seconds)}`) : html`<div class="pf-empty">Sin datos de géneros todavía.</div>`,
        'Cuántos juegos de las bibliotecas tienen cada género (un juego cuenta en cada uno de los suyos).')}</div>
      <div>${section('platforms', 'Por plataforma', count.platforms, d.platforms.length ? bars(d.platforms, (r) => r.platform_name, (r) => r.games, (r) => ` · ${plural(r.players, 'jugador', 'jugadores')}`) : html`<div class="pf-empty">Sin datos de plataformas todavía.</div>`,
        'Cuántos juegos se han tenido en cada plataforma.')}</div>
    </div>

    ${value ? section('value', 'Rentabilidad', count.value, valueView(value),
      `Cuánto cuesta de media cada hora de un juego, según lo que han apuntado los jugadores. Solo salen los juegos con al menos ${value.min_contributors} jugadores con precio y tiempo jugado, y nunca se enseña el de nadie.`) : ''}`);
}

function onClick(e) {
  const fold = e.target.closest('[data-fold]');
  if (fold) {
    const key = fold.dataset.fold;
    if (!folded.delete(key)) folded.add(key);
    fold.closest('.gl-section').classList.toggle('folded', folded.has(key));
    fold.setAttribute('aria-expanded', String(!folded.has(key)));
    saveFolded();
    return;
  }
  const go = e.target.closest('[data-go]');
  if (!go) return;
  const target = main.querySelector(`#gl-${go.dataset.go}`);
  if (folded.delete(go.dataset.go)) { // a folded section opens when it is asked for
    target.classList.remove('folded');
    target.querySelector('[data-fold]').setAttribute('aria-expanded', 'true');
    saveFolded();
  }
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export async function render(ctx) {
  main = ctx.main;
  folded = loadFolded();
  main.onclick = onClick;
  mount(main, html`<div class="loading-spinner">Cargando la biblioteca...</div>`);
  try {
    [data, value] = await Promise.all([api('/group/library'), api('/group/value').catch(() => null)]); // the rest works without it
    if (data) draw(data);
  } catch (err) {
    mount(main, html`<div class="pf-empty">Error cargando la biblioteca del grupo: ${err.message}</div>`);
  }
}
