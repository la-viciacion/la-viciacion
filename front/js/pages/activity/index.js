// Activity page (#/activity): the latest activity of everybody, newest first and by day. GET /activity (derived from the
// sessions, library, ratings and achievements; nothing is stored).
import { api } from '../../lib/api.js';
import { dayLabel, groupByDay } from '../../lib/activity.js';
import { formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { hydratePhotos, playerAvatar } from '../../ui/avatar.js';
import { scoreBadge } from '../../ui/score-badge.js';

export const active = null; // it belongs to no item of the top bar

const PAGE = 30;

let main;
let events = [];
let hasMore = false;

const game = (e) => html`<a class="game-link" href="${gameHref(e.game_id)}">${e.game_name}</a>`;

// What each kind of event says; the player's name goes first, in bold.
const SENTENCES = {
  played: (e) => html`jugó ${formatDuration(e.seconds)} a ${game(e)}`,
  started: (e) => html`empezó ${game(e)}`,
  completed: (e) => html`completó ${game(e)} ${scoreBadge(e.score)}`,
  rated: (e) => html`puntuó ${game(e)} ${scoreBadge(e.score)}`,
  achievement: (e) => (e.hidden
    ? html`desbloqueó un logro oculto`
    : html`desbloqueó el logro «${e.title}»${e.game_id ? html` en ${game(e)}` : ''}`),
};

const eventRow = (e) => html`
  <li class="ac-event">
    ${playerAvatar(e)}
    <div class="ac-text"><strong>${e.name}</strong> ${SENTENCES[e.type](e)}</div>
  </li>`;

function draw() {
  mount(main, html`
    <div class="section-header"><h2 class="section-title">Actividad</h2><div class="section-line"></div></div>
    ${events.length
      ? html`
        ${groupByDay(events).map((g) => html`
          <div class="ac-day">${dayLabel(g.day)}</div>
          <ul class="ac-list pf-card">${g.events.map(eventRow)}</ul>`)}
        ${hasMore ? html`<button class="pf-btn" type="button" id="acMore">Mostrar más</button>` : ''}`
      : html`<div class="pf-empty">Todavía no hay actividad.</div>`}`);
  hydratePhotos(main);
  main.querySelector('#acMore')?.addEventListener('click', loadMore);
}

async function loadMore() {
  const page = await api(`/activity?limit=${PAGE}&offset=${events.length}`);
  if (!page) return;
  events = events.concat(page.items);
  hasMore = page.has_more;
  draw();
}

export async function render(ctx) {
  main = ctx.main;
  events = [];
  hasMore = false;
  try {
    await loadMore();
  } catch (err) {
    mount(main, html`<div class="pf-empty">Error cargando la actividad: ${err.message}</div>`);
  }
}
