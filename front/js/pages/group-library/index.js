// Group library page (#/library): the libraries of the whole group at once. Hidden gems (few have them, those who rated
// them like them), the graveyard (games players gave up), rarities (games only one player has), the most wished games, what several players play or finish,
// the sagas (franchises with two games or more) and what the libraries cover by genre and platform. GET /group/library; derived, nothing is stored.
// A row of pills at the top reaches every section at once (it unfolds the section and scrolls to it), and each section
// folds on its own; what the viewer folded is remembered in this browser.
import { api } from '../../lib/api.js';
import { createFolds, showFold, toggleFold } from '../../lib/fold.js';
import { formatDate, formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { iconChevron } from '../../ui/icons.js';
import { scoreBadge } from '../../ui/score-badge.js';

export const active = 'library';

let main;
let data;
let folded = createFolds('gl-folded'); // the sections the viewer has folded: they start open

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
  ['wanted', 'Los más deseados', d.wanted.total],
  ['together', 'Lo que une al grupo', d.together.total],
  ['finished', 'Terminados por varios', d.finished.total],
  ['sagas', 'Sagas', d.sagas.total],
  ['genres', 'Por género', d.genres.length],
  ['platforms', 'Por plataforma', d.platforms.length],
];

/** When a wished game comes out: the date, "sin fecha" for an announced one without it or that it is already out. */
const releaseLine = (g) => (g.upcoming ? (g.release_date ? `sale el ${formatDate(g.release_date)}` : 'sin fecha de salida') : 'ya ha salido');

const more = (total, shown) => (total > shown ? html`<div class="pf-sub">y ${total - shown} más</div>` : '');

function draw(d) {
  const { summary } = d;
  const count = Object.fromEntries(sectionsOf(d).map(([key, , n]) => [key, n]));
  mount(main, html`
    <div class="wl-head"><h1 class="pf-title">Biblioteca del grupo</h1></div>
    <p class="pf-sub cal-intro">Las bibliotecas de todos juntas: lo que casi nadie conoce, lo que se abandona, lo que se espera y lo que se juega y se termina entre varios.</p>
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

    ${section('wanted', 'Los más deseados', count.wanted, html`
      ${gameList(d.wanted.items, (g) => `${g.wanters.join(', ')} · ${releaseLine(g)}`, 'Nadie tiene nada en su lista de deseos.')}
      ${more(d.wanted.total, d.wanted.items.length)}`,
      'Lo que más jugadores activos esperan, con quién lo desea y cuándo sale.')}

    ${section('together', 'Lo que une al grupo', count.together, html`
      ${gameList(d.together.items, (g) => `${plural(g.players, 'jugador', 'jugadores')} en ${g.season} · ${formatDuration(g.seconds)} entre todos`, 'Todavía ningún juego lo han jugado dos personas en la misma temporada.')}
      ${more(d.together.total, d.together.items.length)}`,
      'Juegos que dos o más jugadores han jugado en una misma temporada (se enseña la temporada con más gente).')}

    ${section('finished', 'Terminados por varios', count.finished, html`
      ${gameList(d.finished.items, (g) => `${g.completed} de ${g.players} lo han terminado${g.mean_seconds ? ` · de media ${formatDuration(g.mean_seconds)}` : ''}`, 'Ningún juego lo han terminado dos personas.')}
      ${more(d.finished.total, d.finished.items.length)}`,
      'Juegos que han completado dos o más jugadores y lo que han tardado de media.')}

    ${section('sagas', 'Sagas', count.sagas, html`
      ${d.sagas.items.length ? html`${bars(d.sagas.items, (r) => r.saga, (r) => r.games, (r) => ` · ${plural(r.players, 'jugador', 'jugadores')} · ${formatDuration(r.seconds)}`)}${more(d.sagas.total, d.sagas.items.length)}` : html`<div class="pf-empty">Ninguna franquicia tiene dos juegos en las bibliotecas.</div>`}`,
      'Franquicias (según IGDB) con al menos dos juegos en las bibliotecas del grupo.')}

    <div class="pf-cols">
      <div>${section('genres', 'Por género', count.genres, d.genres.length ? bars(d.genres, (r) => r.genre, (r) => r.games, (r) => ` · ${formatDuration(r.seconds)}`) : html`<div class="pf-empty">Sin datos de géneros todavía.</div>`,
        'Cuántos juegos de las bibliotecas tienen cada género (un juego cuenta en cada uno de los suyos).')}</div>
      <div>${section('platforms', 'Por plataforma', count.platforms, d.platforms.length ? bars(d.platforms, (r) => r.platform_name, (r) => r.games, (r) => ` · ${plural(r.players, 'jugador', 'jugadores')}`) : html`<div class="pf-empty">Sin datos de plataformas todavía.</div>`,
        'Cuántos juegos se han tenido en cada plataforma.')}</div>
    </div>
`);
}

function onClick(e) {
  const fold = e.target.closest('[data-fold]');
  if (fold) {
    toggleFold(folded, fold.dataset.fold, fold.closest('.gl-section'), fold);
    return;
  }
  const go = e.target.closest('[data-go]');
  if (!go) return;
  const target = main.querySelector(`#gl-${go.dataset.go}`);
  if (folded.set(go.dataset.go, false)) showFold(target, target.querySelector('[data-fold]'), false); // a folded section opens when it is asked for
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export async function render(ctx) {
  main = ctx.main;
  folded = createFolds('gl-folded');
  main.onclick = onClick;
  mount(main, html`<div class="loading-spinner">Cargando la biblioteca...</div>`);
  try {
    data = await api('/group/library');
    if (data) draw(data);
  } catch (err) {
    mount(main, html`<div class="pf-empty">Error cargando la biblioteca del grupo: ${err.message}</div>`);
  }
}
